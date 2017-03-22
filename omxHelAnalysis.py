#! /usr/bin/env python3

# Purpose: This program analyses company data to find cheap stocks

# Operating principle:
# 1. Create dictionaries that include: companies, their ID:s for kauppalehti, their ticker numbers for Yahoo
# 2. Create data frames of financial data necessary for company filtering
# 3. Save all downloadable data to pickles and shelves to speedup runtime
# 4. Create filters for each indicator
# 5. Filter the companies and return list of companies that pass the filters
# x. Create helpers to refine data frames and to weed out incorrect data


import pandas as pd
import numpy as np
from xml.etree import ElementTree as ET
import requests, bs4, re, urllib, os, pprint, shelve

# ________________________________________________________
### CONSTRUCT DATA FRAMES:

def get_turnover_assets_data(company_id):
    url = "http://www.kauppalehti.fi/5/i/porssi/porssikurssit/osake/tulostiedot.jsp?klid=" + company_id
    df = pd.read_html(url)
    df = df[6].iloc[[0, 1, 4]]
    df = df.transpose()
    df.rename(columns={0:"Year", 1:"Turnover", 4:"Adj. Net Current Assets"}, inplace=True)
    df = df.iloc[1:]
    df["Year"] = [2016,2015,2014,2013,2012]
    df.set_index("Year", inplace=True)
    df["Turnover"] = df["Turnover"].str.replace(u'\xa0', '')  # spaces are coded in unicode
    df["Adj. Net Current Assets"] = df["Adj. Net Current Assets"].str.replace(u'\xa0', '')  # spaces are coded in unicode
    df = df.apply(pd.to_numeric)   # May cause problems when downloading table values with "-", fix: manually deactivate
    return df

def get_pe_eps_data(company_id):
    url = "http://www.kauppalehti.fi/5/i/porssi/porssikurssit/osake/tulostiedot.jsp?klid=" + company_id
    df = pd.read_html(url)
    df = df[10].iloc[[0, 5, 7, 9]]
    df = df.transpose()
    df.rename(columns={0: "Year", 5: "P/B", 7: "P/E", 9: "Earnings per Share"}, inplace=True)
    df = df.iloc[1:]
    df["Year"] = [2016,2015,2014,2013,2012]
    df.set_index("Year", inplace=True)
    df = df.apply(pd.to_numeric)   # May cause problems when downloading table values with "-", fix: manually deactivate
    return df

def get_dividend_data(company_id):
    url = "http://www.kauppalehti.fi/5/i/porssi/osingot/osinkohistoria.jsp?klid=" + company_id
    df = pd.read_html(url)
    df = df[5]
    df.rename(columns={0:"Year", 2:"Adj. Dividend"}, inplace=True)
    df = df[["Year", "Adj. Dividend"]].iloc[1:]
    df["Year"] = df["Year"].apply(pd.to_numeric)
    df.set_index("Year", inplace=True)
    df = df.apply(pd.to_numeric)    # May cause problems when downloading table values with "-", fix: manually deactivate
    # Check for duplicated indexes (multiple dividens/year)
    ar = df.index.duplicated()
    if True in ar:
        df = sum_dividends(df)  # method will also convert dividends to numeric
    return df

def get_current_ratio(company_id):
    url = "http://www.kauppalehti.fi/5/i/porssi/porssikurssit/osake/tulostiedot.jsp?klid=" + company_id
    df = pd.read_html(url)
    df = df[9].iloc[[0, 1]]
    df = df.transpose()
    df.rename(columns={0: "Year", 1: "Current Ratio"}, inplace=True)
    df = df.iloc[1:]
    df["Year"] = [2016, 2015, 2014, 2013, 2012]
    df.set_index("Year", inplace=True)
    df = df.apply(pd.to_numeric)  # May cause problems when downloading table values with "-", fix: manually deactivate
    return df

def get_last_price(company_ticker):
    url = "http://chartapi.finance.yahoo.com/instrument/1.0/" + company_ticker + ".HE/chartdata;type=quote;range=1m/csv"
    source_code = urllib.request.urlopen(url).read().decode("latin-1")  # some company names have ääkköset which requires "latin-1" decoding instead of "utf-8"
    stock_data = []
    # splitting the data into lines
    split_source = source_code.split("\n")
    # unifying the data by removing general info at the top of the csv
    for line in split_source:
        split_line = line.split(",")
        if len(split_line) == 6:  # include only lines with 6 values on it
            if "values" not in line and "labels" not in line:  # exclude lines with str"Values" included on line
                stock_data.append(line)
    # take the data and sort it into respective variables
    date, closep, highp, lowp, openp, volume = \
        np.loadtxt(stock_data,
                   delimiter=",",
                   unpack=True)
    return closep[len(stock_data)-1]    # latest stock closing price

def combine_datasets(one, two, three, four):
    df = one.join(two, how="outer")
    df = df.join(three, how="outer")
    df = df.join(four, how="outer")
    return df

def get_company_tickers():
    url = "http://www.nasdaqomxnordic.com/shares/listed-companies/helsinki"
    res = requests.get(url)
    res.raise_for_status()
    soup = bs4.BeautifulSoup(res.text, "lxml")
    elem = soup.find_all("tr")    # is a resultsSet
    # make a list of lists where each item has the cells of one line of the table
    tableList = []  # list of lists that represents the table
    headerList = [] # list of table headers
    for tag in elem[0].find_all("th"):
        headerList.append(tag.text)
    tableList.append(headerList)
    for line in elem:
        set = line.find_all("td")
        lineList = []   # list of values that represents one line in the table
        for tag in set:
            lineList.append(tag.text)
        tableList.append(lineList)
    df = pd.DataFrame(tableList)    # is the table as a dataframe w/o headers
    df.rename(columns={0: "Name", 1: "Symbol", 2: "Currency", 3: "ISIN", 4: "Sector", 5:"ICB Code", 6: "Fact sheet"}, inplace=True)
    df = df.iloc[2:]
    df = df[["Name", "Symbol", "ISIN", "Sector", "ICB Code"]]
    df = df.reset_index(drop=True)
    return df

def get_share_qty(company_id):  # uncompleted
    url = "http://www.kauppalehti.fi/5/i/porssi/porssikurssit/osake/index.jsp?klid=" + company_id
    res = requests.get(url)
    res.raise_for_status()
    soup = bs4.BeautifulSoup(res.text, "lxml")
    #elem = soup.select("[class~=table_stock_basic_details]")
    elem = soup.find_all("table")
    #pprint.pprint(elem[18]) # Osakkeen perustiedot table
    elem2 = str(elem[18])

    table = ET.XML(elem2)
    rows = iter(table)
    headers = [col.text for col in next(rows)]
    for row in rows:
        values = [col.text for col in row]
        print(dict(zip(headers, values)))
    print(headers)
    #pprint.pprint(elem[20]) # Kurssikehitys table 12kk muutos

    #table = soup.find("table", attrs={"class":"table_stock_basic_details"})
    #headings = [td.get_text() for td in table.find("td").find_all("td")]
    #datasets = []
    #for row in table.find_all("td")[1:]:
    #    dataset = (headings, (td.get_text() for td in row.find_all("td")))
    #    datasets.append(dataset)
    #print(datasets)
    #for dataset in datasets:
    #    for field in dataset:
    #        print("{0:<16}: {1}".format(field[0], field[1]))
    #return datasets

# ________________________________________________________
### CREATING PICKLES:

# Create company pickles from live data using existing company_dictionary
def create_df_pickles(company_dictionary):
    if not os.path.exists(".\\omxHelAnalysis"):
        os.makedirs("omxHelAnalysis", exist_ok=True)
    for compId in company_dictionary.values():
        try:
            df = combine_datasets(
                get_turnover_assets_data(compId),
                get_pe_eps_data(compId),
                get_current_ratio(compId),
                get_dividend_data(compId))
            save_df_to_pickle(compId, df)
            print("Data frame for companyID: " + str(compId) + ", saved to file: " + str(compId) + ".pickle")
        except Exception as err:
            print("An exception happened: " + str(err))

def save_df_to_pickle(company_id, df):
    if not os.path.exists(".\\omxHelAnalysis"):
        os.makedirs("omxHelAnalysis", exist_ok=True)
    pickleName = str(company_id) + ".pickle"
    pickleLocation = ".\\omxHelAnalysis\\" + pickleName
    df.to_pickle(pickleLocation)
    return pickleName

def load_company_data_pickle(company_id):
    pickleName = str(company_id) + ".pickle"
    pickleLocation = ".\\omxHelAnalysis\\" + pickleName
    df = pd.read_pickle(pickleLocation)
    return df

# ________________________________________________________
### GENERATING COMPANY DICTIONARIES:

# Getting company IDs:
def get_company_id_list():
    company_id_list = []
    url = "http://www.kauppalehti.fi/5/i/porssi/porssikurssit/"
    res = requests.get(url)
    res.raise_for_status()
    soup = bs4.BeautifulSoup(res.text, "lxml")
    linkList = soup.find_all("a")
    endsWithNumber = re.compile(r'\d{4}$')
    for link in linkList:
        href = link.get("href")
        href = str(href)
        mo = endsWithNumber.search(href)
        if mo != None:
            if mo.group() not in company_id_list:
                company_id_list.append(mo.group())

    return company_id_list


# Create dictionary with structure {compName : compTickers["Symbol"]
def create_company_symbol_dictionary(compDict, compTickersDf):
    beforeParenthesis = re.compile(r"""(
                            (\w*)           # 1 First word
                            (\s|-|'|&)*     # 2 separator
                            (\w*)           # 3 Second word
                            (\s|-|'|&)*     # 4 separator
                            (\w*)           # 5 Third word
                            (\s|-|'|&)*     # 6 separator
                            (\w*)           # 7 Fourth word
                            (\s\(\w+\))     # 8 symbol in parenthesis and the space before it
                            )""", re.VERBOSE | re.IGNORECASE)
#    pprint.pprint(compTickersDf)
    dictionary = {}
    companyNameList = []
    missingTickers = {}
    #print(compTickersDf)
    for compName in compDict.keys():    # Creates a list of plain text company names from compDict
        mo = beforeParenthesis.search(compName)
        s = str(mo.group(0))
        l = len(mo.group(9))
        s = s[:-l]
        companyNameList.append(s)
    for i in companyNameList:   # Searches the CompTickers df for matches to the companyNamesList and returns the Symbol value
        df = compTickersDf.loc[compTickers["Name"] == i]["Symbol"]
        df = df.reset_index(drop=True)
        df = np.array(df)
        df = "".join(df)
        if len(df) > 0:
            dictionary[i] = df
        if len(df) == 0:    # company name was not found in compTickers
            missingTickers[i] = df
    print("missing dictiotionary")
    pprint.pprint(missingTickers.keys())
    return dictionary

# Create dictionary with structure {compDict.keys() : compTickers["Symbol"]
def create_company_symbol_dictionary2(compDict, compTickersDf):
    beforeParenthesis = re.compile(r"""(
                            (\w*)           # 1 First word
                            (\s|-|'|&)*     # 2 separator
                            (\w*)           # 3 Second word
                            (\s|-|'|&)*     # 4 separator
                            (\w*)           # 5 Third word
                            (\s|-|'|&)*     # 6 separator
                            (\w*)           # 7 Fourth word
                            (\s\(\w+\))     # 8 symbol in parenthesis and the space before it
                            )""", re.VERBOSE | re.IGNORECASE)
    dictionary = {}
    companyNameDict = {}
    missingTickers = {}
    for compName in compDict.keys():    # Creates a list of plain text company names from compDict
        mo = beforeParenthesis.search(compName)
        s = str(mo.group(0))
        l = len(mo.group(9))
        s = s[:-l]
        companyNameDict[compName] = s
    for i in companyNameDict.keys():   # Searches the CompTickers df for matches to the companyNamesList and returns the Symbol value
        df = compTickersDf.loc[compTickers["Name"] == companyNameDict[i]]["Symbol"]
        df = df.reset_index(drop=True)
        df = np.array(df)
        df = "".join(df)
        if len(df) > 0:
            dictionary[i] = df  # matches compDict.key()
        if len(df) == 0:    # company name was not found in compTickers
            missingTickers[i] = df
    return dictionary

# Getting company name:
def get_company_name(company_id):
    url = "http://www.kauppalehti.fi/5/i/porssi/porssikurssit/osake/tulostiedot.jsp?klid=" + company_id
    res = requests.get(url)
    res.raise_for_status()
    soup = bs4.BeautifulSoup(res.text, "lxml")
    return soup.find_all("h1")[1].get_text()

# Create a dictionary in the format {companyName:CompanyId}
def company_dictionary():
    dictionary = {}
    for compId in get_company_id_list():
        dictionary[get_company_name(compId)] = compId
    return dictionary

# Create a dictionary of company dataframes {companyName:df_pickle_Name}
def dataFrame_dictionary(compDictionary):
    dictionary = {}
    for compName in list(compDictionary.keys()):
        dictionary[compName] = combine_datasets(
            get_turnover_assets_data(compDictionary[compName]),
            get_pe_eps_data(compDictionary[compName]),
            get_dividend_data(compDictionary[compName]))
    return dictionary

def get_price_dictionary(compTickersDict):
    dictionary = {}
    for stock in compTickersDict.keys():
        try:
            dictionary[stock] = float(get_last_price(compTickersDict[stock]))
        except:
            print("Could not get price for: " + str(stock))
            dictionary[stock] = np.nan
    return dictionary

# ________________________________________________________
### ERROR CHECKING:
def list_missing_df(compDictionary):
    missingIds = []
    for compName in compDictionary.keys():
        company_id = compDictionary[compName]
        pickleName = str(company_id) + ".pickle"
        pickleLocation = ".\\omxHelAnalysis\\" + pickleName
        if not os.path.exists(pickleLocation):
            missingIds.append(company_id)
            print("Missing data for company: " + compName + ", id: " + company_id)
    return missingIds

def create_df_pickles_from_Idlist(listOfIds):
    for compId in listOfIds:
        try:
            df = combine_datasets(
                get_turnover_assets_data(compId),
                get_pe_eps_data(compId),
                get_current_ratio(compId),
                get_dividend_data(compId))
            save_df_to_pickle(compId, df)
            print("Data frame for companyID: " + str(compId) + ", saved to file: " + str(compId) + ".pickle")
        except Exception as err:
            print("An exception happened: " + str(err))

# Create errorList by checking each df for errors
def create_errorList(ListOfIds):
    errorsList = []
    for compId in ListOfIds:
        df = load_company_data_pickle(compId)
        for col in list(df.columns.values):
            try:
                df[col] = df[col].apply(pd.to_numeric)
            except Exception as err:
                print("An exception happened: " + str(err))
                errorsList.append(compId)
    errorsList = list(set(errorsList))  # Removes duplicated values from the list
    return errorsList

def create_errorList2(ListOfIds):
    errorsList = []
    for compId in ListOfIds:
        if not check_df_for_float64(compId):
            errorsList.append(compId)
    errorsList = list(set(errorsList))  # Removes duplicated values from the list
    return errorsList

# Check df if all columns have dtype=float64
def check_df_for_float64(compId):
    df = load_company_data_pickle(compId)
    res = True
    for col in list(df.columns.values):
        if check_column_dtype(df, col) != np.dtype("float64"):
            res = False
    return res

# Check data type for column
def check_column_dtype(df, column):
    return np.array(df[column]).dtype

# Check if df is missing some columns
def check_for_missing_columns(df):
    columnNames = ["Turnover", "Adj. Net Current Assets", "P/E", "P/B", "Earnings per Share", "Adj. Dividend"]
    count = 0
    if len(list(df.columns.values)) < len(columnNames):
        count += 1
    else:
        for col in list(df.columns.values):
            if col not in columnNames:
                count += 1
    if count > 1:
        return True
    else:
        return False

# Check if df is missing some columns
def check_for_missing_columns2(df):
    columnNames = ["Turnover", "Adj. Net Current Assets", "P/E", "P/B", "Earnings per Share", "Adj. Dividend"]
    count = 0
    for col in columnNames:
        if col not in list(df.columns.values):
            count += 1
    if count > 0:
        return True
    else:
        return False

# ________________________________________________________
### ERROR HANDLING:

# Changing df to numeric and removing unicode character \xa0
def convert_pickled_df_to_numeric(compId):
    df = load_company_data_pickle(compId)
    for col in list(df.columns.values):
        try:
            df[col] = df[col].str.replace(u'\xa0', '')  # spaces are coded in unicode
            df[col] = df[col].apply(pd.to_numeric)  # converts values to numeric
        except Exception as err:
            print("An exception occurred: " + str(err))
            if compId != None:
                print(compId)
    return df

# Changing values in dfs
def convert_column_error_to_NaN(compId, column):
    df = load_company_data_pickle(compId)
    df[column] = pd.to_numeric(df[column], errors="coerce")
    return df

def convert_column_unicode_thousand(compId, column):
    df = load_company_data_pickle(compId)
    df[column] = df[column].str.replace(u'\xa0', '')  # spaces are coded in unicode
    df[column] = pd.to_numeric(df[column])
    return df

# Changing all values in dfs to numeric with coerce
def convert_error_to_NaN_coerce(compId):
    df = load_company_data_pickle(compId)
    for col in list(df.columns.values):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

# Replacing "-" with NaN-values
def convert_line_to_empty(compId):
    df = load_company_data_pickle(compId)
    for col in list(df.columns.values):
        try:
            df[col] = df[col].str.replace('-', "")
        except Exception as err:
            print("An exception occurred: " + str(err))
            if compId != None:
                print(compId)
    return df

# In case of multiple dividends sum them up to one index value (year)
def sum_dividends(df):
    df = df.apply(pd.to_numeric)  # converts values to numeric
    df = df.groupby(df.index).sum() # sum all values together that have same index value
    return df

# Rename keys in a dictionary
def rename_dict_keys(dictionary):
    for key in dictionary.keys():
        print(key)
        rename = input("Do you want to rename key? (input_new_key/n)")
        if rename != "n":
            dictionary[rename] = dictionary.pop[key]
    return dictionary

# update values in a df column
def change_column_values(df, column):
    i = 0
    while i < len(df):
        a = df.iloc[i][column]
        print(a)
        b = input("rename: (empty/input)")  # will take any non empty string as the new value for the df cell
        if b != "":
            df.set_value(i, column, b)
            print(df.iloc[i][column])
        i += 1
    return df


# ________________________________________________________
### FINANCIAL FILTERS:

# 1. Adequate Size of the Enterprise
def filter_adequate_size(df):
    df.sort_index(ascending=False, inplace=True)
    turnoverLimit = 100 # 100 million €
    if df.iloc[1]["Turnover"] > turnoverLimit:
        return True
    else:
        return False

def p_filter_adequate_size(df):
    df.sort_index(ascending=False, inplace=True)
    turnover = df.iloc[1]["Turnover"]
    return turnover

# 2. Sufficiently Strong Financial Condition


# 3. Earning Stability
def filter_earning_stability(df):
    df.sort_index(ascending=False, inplace=True)
    df = df["Earnings per Share"]
    df.dropna(how="any", inplace=True)
    df.sort_index(ascending=False, inplace=True)
    epsLimit = 0    # some earnings each year
    span = min(len(df.index), 10)   # for 10 year or if not enough data than max of data
    df = df.iloc[:span]
    i = 0
    for val in df:
        if val <= epsLimit:
            i += 1
    if i > 0:
        return False
    else:
        return True

def p_filter_earning_stability(df):
    df.sort_index(ascending=False, inplace=True)
    df = df["Earnings per Share"]
    df.dropna(how="any", inplace=True)
    df.sort_index(ascending=False, inplace=True)
    years = min(len(df.index), 10)  # for 10 year or if not enough data than max of data
    df = df.iloc[:years]
    low = 99999
    for val in df:
        low = min(low, val)
    return years, low

# 4. Dividend Record
def filter_dividend_record(df):
    df.sort_index(ascending=False, inplace=True)
    divHist = 0  # some dividends payed uninterrupted for past 20 years
    span = min(len(df.index), 20)   # for 20 years or if not enough data then max of data
    df = df["Adj. Dividend"].iloc[:span]
    df.dropna(how="any", inplace=True)
    i = 0
    for val in df:
        if val == divHist:
            i += 1
    if i > 0:
        return False
    else:
        return True

def p_filter_dividend_record(df):
    df.sort_index(ascending=False, inplace=True)
    years = min(len(df.index), 20)  # for 20 years or if not enough data then max of data
    df = df["Adj. Dividend"].iloc[:years]
    df.dropna(how="any", inplace=True)
    low = 99999
    for val in df:
        low = min(low, val)
    return years, low

# 5. Earnings Growth
def filter_earnings_growth(df):
    df.sort_index(ascending=False, inplace=True)
    eGrowth = 1/3  # earnings growth by 1/3 in last 10 years
    df = df["Earnings per Share"]
    df.dropna(how="any", inplace=True)
    span = min(len(df.index), 10)   # for 10 years or if not enough data then max of data
    if span > 6:
        dfLately = df.iloc[:3].sum() /3
        dfEarly = df.iloc[len(df.index)-3:].sum() /3
        if dfEarly > 0:
            eg = dfLately / dfEarly - 1
        else:
            eg = -1
    elif 4 < span < 6:
        dfLately = df.iloc[:2].sum() /2
        dfEarly = df.iloc[3:5].sum() /2
        if dfEarly > 0:
            eg = dfLately/dfEarly-1
        else:
            eg = -1
    else:
        eg = -1
    if eg >= eGrowth:
        if dfEarly >= 0 and dfLately >= 0:
            return True
        else:
            return False
    else:
        return False

def p_filter_earnings_growth(df):
    df.sort_index(ascending=False, inplace=True)
    df = df["Earnings per Share"]
    df.dropna(how="any", inplace=True)
    years = min(len(df.index), 10)  # for 10 years or if not enough data then max of data
    if years > 6:
        dfLately = df.iloc[:3].sum() / 3
        dfEarly = df.iloc[len(df.index) - 3:].sum() / 3
        if dfEarly > 0:
            growth = dfLately / dfEarly - 1
        else:
            growth = -1
    elif 4 < years < 6:
        dfLately = df.iloc[:2].sum() / 2
        dfEarly = df.iloc[3:5].sum() / 2
        if dfEarly > 0:
            growth = dfLately / dfEarly - 1
        else:
            growth = -1
    else:
        growth = -1
    return years, growth

# 6. Moderate Price/Earnings Ratio
def filter_moderate_PE_ratio(df, price):
    df.sort_index(ascending=False, inplace=True)
    df = df["Earnings per Share"]
    df.dropna(how="any", inplace=True)
    years = 3
    PElimit = 15
    i = 0
    s = 0
    while i < years:
        s += df.iloc[i]
        i += 1
    average = s / years
    if average == 0:
        pe = 0
    else:
        pe = price / average
    if 0 < pe < PElimit:
        return True
    else:
        return False

def p_filter_moderate_PE_ratio(df, price):
    df.sort_index(ascending=False, inplace=True)
    df = df["Earnings per Share"]
    df.dropna(how="any", inplace=True)
    years = 3
    i = 0
    s = 0
    while i < years:
        s += df.iloc[i]
        i += 1
    average = s / years
    if average == 0:
        pe = 0
    else:
        pe = price / average
    return years, pe

# 7. Moderate Ratio of Price to Assets
def filter_moderate_Price_to_Assets_ratio(df):
    df.sort_index(ascending=False, inplace=True)
    df.dropna(how="any", inplace=True)
    df = df[["P/B", "P/E"]]
    PBlimit = 1.5
    PExPBlimit = 22.5
    if len(df) < 1:
        return False
    elif df["P/B"].iloc[0] > PBlimit:
        return False
    elif df["P/E"].iloc[0] * df["P/B"].iloc[0] > PExPBlimit:
        return False
    else:
        return True

def p_filter_moderate_Price_to_Assets_ratio(df):
    df.sort_index(ascending=False, inplace=True)
    df.dropna(how="any", inplace=True)
    df = df[["P/B", "P/E"]]
    PB = df["P/B"].iloc[0]
    PExPB = df["P/E"].iloc[0] * df["P/B"].iloc[0]
    return PB, PExPB

# ________________________________________________________
### START OF RUNTIME:

# Loading company dictionary from a shelve file into variable compDict
shelfFile = shelve.open("omxHelVariable")
compDict = shelfFile["dict"]
errorsList = shelfFile["errorsList"]
compTickers = shelfFile["compTickers"]
priceDict = shelfFile["priceDict"]
compTickersDict = shelfFile["compTickersDict"]

#pprint.pprint(compDict)

#currentID = "1901"
#create_df_pickles_from_Idlist([currentID])
#print(load_company_data_pickle(currentID))
#print(get_pe_eps_data(currentID))
#print(filter_moderate_Price_to_Assets_ratio(load_company_data_pickle(currentID)))



#Filtered results:
fAdequateSize = []      # List of companies passing Adequate Size
fEarningsStability = [] # List of companies passing Earnings Stability
fDividendRecord = []    # List of companies passing Dividend Record
fModeratePEratio = []   # List of companies passing Moderate PE Rate
fEarningsGrowth = []    # List of companies passing Earning Growth
fModeratePtoAratio = [] # List of companies passing Moderate Price to Assets Ratio
fCombined = []          # List of companies passing All Filters


# FILTERING::::::::::::::::::::::::::::::::::
# Exclude missing dfs from compDict
missingDfList = list_missing_df(compDict)
missingDfList.append(compDict["Endomines AB (ENDO)"])
missingDfList.append(compDict["Aktia Pankki Oyj (AKT)"])
missingDfList.append(compDict["SSAB (SSAB)"])
missingDfList.append(compDict["Qt Group (QTCOM)"])
workingIdList = []
for compId in compDict.values():
    if compId not in missingDfList:
        workingIdList.append(compId)

pprint.pprint(workingIdList)
print(len(workingIdList))

# PROTOCAL: Update data from website
if input("Update all df:s from Kauppalehti? (y/n)") == "y":
    create_df_pickles(compDict)

# Check for errors::::::::::::::::::::::::::::
if input("Refresh errorsList? (y/n)") == "y":
    IdList = compDict.values()
    # Refresh the missingDfList
    missingDfList = list_missing_df(compDict)
    print("MissingDfList:")
    pprint.pprint(missingDfList)
    # Refresh errorsList (effectively checks if df is convertible to numeric or not)
    checkList = []
    for compId in IdList:
        if compId not in missingDfList:
            checkList.append(compId)
    errorsList = create_errorList2(checkList)
    shelfFile["errorsList"] = errorsList
    print("ErrorsList:")
    print(errorsList)

if input("Create a list of df:s that are missing columns? (y/n)") == "y":
    dfsWithMissingColumns = []
    for comp in workingIdList:
        if check_for_missing_columns2(load_company_data_pickle(comp)):
            dfsWithMissingColumns.append(comp)
    print("These df:s are missing some columns:")
    pprint.pprint(dfsWithMissingColumns)

    if input("Update df:s for these companies from Kauppalehti? (y/n)") == "y":
        create_df_pickles_from_Idlist(dfsWithMissingColumns)

if input("Set errorList to all except those which do not have df:s? (y/n)") == "y":
    IdList = compDict.values()
    # Refresh the missingDfList
    missingDfList = list_missing_df(compDict)
    print("MissingDfList:")
    pprint.pprint(missingDfList)
    # Refresh errorsList (effectively checks if df is convertible to numeric or not)
    checkList = []
    for compId in IdList:
        if compId not in missingDfList:
            checkList.append(compId)
    errorsList = checkList
    shelfFile["errorsList"] = errorsList
    print("ErrorsList:")
    print(errorsList)

# Check and repair df:s on the errors list
if input("Enter error checking for items on errorsList? (y/n)") == "y":
    for currentId in errorsList:
        print(get_company_name(currentId))
        print(currentId)
        print(load_company_data_pickle(currentId))

        if input("Do you want reload df from website? (y/n)") == "y":
            # Reload df from website
            create_df_pickles_from_Idlist([currentId])
            print(load_company_data_pickle(currentId))

        if input("Do you want to convert columns to num with coerce? (y/n)") == "y":
            # Convert one column to num with coerce
            df = convert_error_to_NaN_coerce(currentId)
            print(df)
            save_df_to_pickle(currentId, df)

        if input("Do you want to convert - to empty? (y/n)") == "y":
            # Convert "-" to ""
            save_df_to_pickle(currentId, convert_line_to_empty(currentId))
            print(load_company_data_pickle(currentId))

        if input("Do you want convert pickles to numeric and fix unicode? (y/n)") == "y":
            # convert pickles to numeric and fix unicode
            df = convert_pickled_df_to_numeric(currentId)
            print(df)
            save_df_to_pickle(currentId, df)


# PROTOCAL: Do the stock screening

if input("Enter stock screening? (y/n)") == "y":
    print(":::::::::::::::::::::::::::::::::::::::::")
    print("Filter adequate size: ")
    for comp in compDict.keys():
        compId = compDict[comp]
        if compId in workingIdList:
            if filter_adequate_size(load_company_data_pickle(compId)):
                fAdequateSize.append(comp)

    print(":::::::::::::::::::::::::::::::::::::::::")
    print("Filter earnings stability: ")
    for comp in compDict.keys():
        compId = compDict[comp]
        if compId in workingIdList:
            if filter_earning_stability(load_company_data_pickle(compId)):
                fEarningsStability.append(comp)

    print(":::::::::::::::::::::::::::::::::::::::::")
    print("Dividend record: ")
    for comp in compDict.keys():
        compId = compDict[comp]
        if compId in workingIdList:
            if filter_dividend_record(load_company_data_pickle(compId)):
                fDividendRecord.append(comp)


    print(":::::::::::::::::::::::::::::::::::::::::")
    print("Moderate P/E ratio: ")
    for comp in compDict.keys():
        compId = compDict[comp]
        if compId in workingIdList:
            try:
                if filter_moderate_PE_ratio(load_company_data_pickle(compId), priceDict[comp]):
                    fModeratePEratio.append(comp)
            except:
                print("Error with: " + str(comp))


    print(":::::::::::::::::::::::::::::::::::::::::")
    print("Earnings Growth: ")
    for comp in compDict.keys():
        compId = compDict[comp]
        if compId in workingIdList:
            if filter_earnings_growth(load_company_data_pickle(compId)):
                fEarningsGrowth.append(comp)


    print(":::::::::::::::::::::::::::::::::::::::::")
    print("Moderate ratio of Price to Assests ratio: ")
    for comp in compDict.keys():
        compId = compDict[comp]
        if compId in workingIdList:
            if filter_moderate_Price_to_Assets_ratio(load_company_data_pickle(compId)):
                fModeratePtoAratio.append(comp)


    print(":::::::::::::::::::::::::::::::::::::::::")
    print("All Filters Combined: ")
    for comp in fAdequateSize:
        if comp in fEarningsGrowth:
            if comp in fDividendRecord:
                if comp in fModeratePEratio:
                    if comp in fEarningsGrowth:
                        if comp in fModeratePtoAratio:
                            fCombined.append(comp)

    print("Adequate size qty: " + str(len(fAdequateSize)))
    print("Earnings stability qty: " + str(len(fEarningsStability)))
    print("Dividend record qty: " + str(len(fDividendRecord)))
    print("Moderate PE ratio qty: " + str(len(fModeratePEratio)))
    print("Earnings growth qty: " + str(len(fEarningsGrowth)))
    print("Moderate Price to Assets ratio qty: " + str(len(fModeratePtoAratio)))
    print("All filters combined qty: " + str(len(fCombined)))
    pprint.pprint(fCombined)

    # Print the data frames for the companies that pass all filters
    for comp in fCombined:
        print(comp)
        print(load_company_data_pickle(compDict[comp]))
        print("Company size:")
        print(p_filter_adequate_size(load_company_data_pickle(compDict[comp])))
        print("Earning stability: (years (10) / lowest value)")
        print(p_filter_earning_stability(load_company_data_pickle(compDict[comp])))
        print("Dividend record: (years (20) / lowest value)")
        print(p_filter_dividend_record(load_company_data_pickle(compDict[comp])))
        print("Earnings growth: (years (10) / growth (0.33))")
        print(p_filter_earnings_growth(load_company_data_pickle(compDict[comp])))


shelfFile.close()