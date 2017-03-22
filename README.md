# omx-stock-screener
# Purpose: This program analyses company data to find cheap stocks according to value investing priciples

# Operating principle:
# 1. Create dictionaries that include: companies, their ID:s for kauppalehti, their ticker numbers for Yahoo
# 2. Create data frames of financial data necessary for company filtering
# 3. Save all downloadable data to pickles and shelves to speedup runtime
# 4. Create filters for each indicator
# 5. Filter the companies and return list of companies that pass the filters
# x. Create helpers to refine data frames and to weed out incorrect data
