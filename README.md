# trulia-scraper
Scraper for real estate listings on Trulia.com implemented in Python with Scrapy.

## Basic usage
To crawl the scraper, you need to install [Python3.6](https://www.python.org/downloads/), as well as the [Scrapy framework](https://scrapy.org/) framework.
To crawl the trulia spider for the state of CA and city of San_Francisco (the default locale), simply run the command
`
scrapy crawl trulia
`from the project directory. To scrape listings for another city, specify the city and state arguments using the -a flag. For example,

`scrapy crawl trulia -a city=Boston -a state=MA`
will scrape all listings reachable from (https://www.trulia.com/MA/Boston/) .

By default, the scraped data will be stored (using Scrapy's feed export) in the data directory as a JSON lines (.jl) file following the naming convention

`data_{sold|for_sale}_{state}_{city}_{time}.jl`

where '{sold|for_sale}' is 'sold' or 'for_sale' for the trulia and trulia_sold spiders, respectively, '{state}' and '{city}' are the specified state and city (e.g. CA and San_Francisco, respectively), 
and '{time}' represents the current UTC time.

If you prefer a different output file name and format, you can specify this from the command line using Scrapy's -o option. For example,

`scrapy crawl trulia_sold -a state=WA -city=Seattle -o data_Seattle.csv`

will output the data in CSV format as `data_Seattle.csv`.
