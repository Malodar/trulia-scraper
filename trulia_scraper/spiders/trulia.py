# -*- coding: utf-8 -*-
import os
import scrapy
import math
import datetime
import json
from scrapy.linkextractors import LinkExtractor
from ..items import TruliaItem, TruliaItemLoader
from trulia_scraper.parsing import get_number_from_string
from scrapy.utils.conf import closest_scrapy_cfg


class TruliaSpider(scrapy.Spider):
    name = 'trulia'
    proxy = 'http://127.0.0.1:24001'
    allowed_domains = ['trulia.com']
    custom_settings = {'FEED_URI': os.path.join(os.path.dirname(closest_scrapy_cfg()), 'data/data_for_sale_%(state)s_%(city)s_%(time)s.jl'),
                       'FEED_FORMAT': 'csv'}

    def __init__(self, state='CA', city='San_Francisco', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state = state
        self.city = city
        self.start_urls = [f'http://trulia.com/{state}/{city}']
        self.le = LinkExtractor(allow=r'^https://www.trulia.com/property')

    def parse(self, response):
        pages_number = self.get_number_of_pages_to_scrape(response)
        self.logger.info(f"Determined that property pages are contained on {pages_number} different index pages, each containing at most 30 properties. Proceeding to scrape each index page...")
        for url in [response.urljoin("{n}_p/".format(n=n)) for n in range(1, pages_number+1)]:
            yield scrapy.Request(url=url,
                                 callback=self.parse_index_page,
                                 meta={
                                     'proxy': self.proxy,
                                 })

    @staticmethod
    def get_number_of_pages_to_scrape(response):
        number_of_results = int(response.css("div[data-testid='pagination-caption']::text").extract_first().split()[2].replace(',', ''))
        return math.ceil(number_of_results/30)

    def parse_index_page(self, response):
        for link in self.le.extract_links(response):
            yield scrapy.Request(url=link.url,
                                 callback=self.parse_property_page,
                                 meta={
                                     'proxy': self.proxy,
                                 })

    def parse_property_page(self, response):
        item = TruliaItem()
        js = json.loads(response.css("script#__NEXT_DATA__::text").extract_first())
        home_details = js['props']['homeDetails']
        item['url'] = response.url
        item['address'] = home_details['location']['streetAddress']
        item['city'] = home_details['location']['city']
        item['state'] = home_details['location']['stateCode']
        try:
            item['price'] = home_details['price']['price']
        except TypeError:
            item['price'] = ''
        except KeyError:
            item['price'] = ''
        item['neighborhood'] = home_details['location']['neighborhoodName']
        # overview = home_details['']
        item['description'] = home_details['description']['value']
        # prices = ",\n".join([f'{i["formattedDate"]} - {i["event"]} - {i["price"]["formattedPrice"].replace(",", "")}' for i in price_history])

        # Property tax information is on 'sold' pages only
        try:
            item['property_tax_assessment_year'] = home_details['taxes']['highlightedAssessments']['year']
        except TypeError:
            item['property_tax_assessment_year'] = ''
        try:
            item['property_tax'] = home_details['taxes']['highlightedAssessments']['taxValue']['formattedPrice']
        except TypeError:
            item['property_tax'] = ''
        try:
            assessments = home_details['taxes']['highlightedAssessments']['assessments']
            for a in assessments:
                if a['type'] == 'Land':
                    item['property_tax_assessment_land'] = a['amount']['formattedPrice']
                if a['type'] == 'Improvements':
                    item['property_tax_assessment_improvements'] = a['amount']['formattedPrice']
        except TypeError:
            item['property_tax_assessment_land'] = ''
            item['property_tax_assessment_improvements'] = ''
        try:
            item['property_tax_assessment_total'] = home_details['taxes']['highlightedAssessments']['totalAssessment']['formattedPrice']
        except TypeError:
            item['property_tax_assessment_total'] = ''
        # property_tax_market_value =

        # The 'Features' sections is on 'for sale' pages only
        features = home_details["features"]["attributes"]
        for f in features:
            try:
                feature_name = f['formattedName']
            except KeyError:
                feature_name = ''
            if feature_name and feature_name == 'Lot Size':
                item['lot_size'] = f['formattedValue']
            if '/sqft' in f['formattedValue']:
                item['price_per_square_foot'] = f['formattedValue'].split('/')[0]
            if 'Built in' in f['formattedValue']:
                item['year_built'] = f['formattedValue'].split()[-1]
            if 'Days on' in f['formattedValue']:
                item['days_on_Trulia'] = f['formattedValue']

        # Items generated from further parsing of 'raw' scraped data
        try:
            item['area'] = home_details['floorSpace']['formattedDimension'].replace(',', '')
        except TypeError:
            item['area'] = ''
        # lot_size_units =
        try:
            item['bedrooms'] = home_details['bedrooms']['formattedValue']
        except TypeError:
            item['bedrooms'] = ''
        try:
            item['bathrooms'] = home_details['bathrooms']['formattedValue']
        except TypeError:
            item['bathrooms'] = ''
        price_history = home_details['priceHistory']
        item['price_history'] = ",\n".join([f'{i["formattedDate"]} - {i["event"]} - {i["price"]["formattedPrice"].replace(",", "")}' for i in price_history])

        # l = TruliaItemLoader(item=TruliaItem(), response=response)
        # self.load_common_fields(item_loader=l, response=response)
        #
        # listing_information = l.nested_xpath('//span[text() = "LISTING INFORMATION"]')
        # listing_information.add_xpath('listing_information', './parent::div/following-sibling::ul[1]/li/text()')
        # listing_information.add_xpath('listing_information_date_updated', './following-sibling::span/text()', re=r'^Updated: (.*)')
        #
        # public_records = l.nested_xpath('//span[text() = "PUBLIC RECORDS"]')
        # public_records.add_xpath('public_records', './parent::div/following-sibling::ul[1]/li/text()')
        # public_records.add_xpath('public_records_date_updated', './following-sibling::span/text()', re=r'^Updated: (.*)')
        #
        # item = l.load_item()
        self.post_process(item=item)
        return item

    # @staticmethod
    # def load_common_fields(item_loader, response):
    #     '''Load field values which are common to "on sale" and "recently sold" properties.'''
    #     item_loader.add_value('url', response.url)
    #     item_loader.add_xpath('address', '//*[@data-role="address"]/text()')
    #     item_loader.add_xpath('city_state', '//*[@data-role="cityState"]/text()')
    #     item_loader.add_xpath('price', '//span[@data-role="price"]/text()', re=r'\$([\d,]+)')
    #     item_loader.add_xpath('neighborhood', '//*[@data-role="cityState"]/parent::h1/following-sibling::span/a/text()')
    #     details = item_loader.nested_css('.homeDetailsHeading')
    #     overview = details.nested_xpath('.//span[contains(text(), "Overview")]/parent::div/following-sibling::div[1]')
    #     overview.add_xpath('overview', css='', xpath='.//li/text()')
    #     overview.add_xpath('area', xpath='.//li/text()', re=r'([\d,]+) sqft$')
    #     overview.add_xpath('lot_size', xpath='.//li/text()', re=r'([\d,.]+) (?:acres|sqft) lot size$')
    #     overview.add_xpath('lot_size_units', xpath='.//li/text()', re=r'[\d,.]+ (acres|sqft) lot size$')
    #     overview.add_xpath('price_per_square_foot', xpath='.//li/text()', re=r'\$([\d,.]+)/sqft$')
    #     overview.add_xpath('bedrooms', xpath='.//li/text()', re=r'(\d+) (?:Beds|Bed|beds|bed)$')
    #     overview.add_xpath('bathrooms', xpath='.//li/text()', re=r'(\d+) (?:Baths|Bath|baths|bath)$')
    #     overview.add_xpath('year_built', xpath='.//li/text()', re=r'Built in (\d+)')
    #     overview.add_xpath('days_on_Trulia', xpath='.//li/text()', re=r'([\d,]) days on Trulia$')
    #     overview.add_xpath('views', xpath='.//li/text()', re=r'([\d,]+) views$')
    #     item_loader.add_css('description', '#descriptionContainer *::text')
    #
    #     price_events = details.nested_xpath('.//*[text() = "Price History"]/parent::*/following-sibling::*[1]/div/div')
    #     price_events.add_xpath('prices', './div[contains(text(), "$")]/text()')
    #     price_events.add_xpath('dates', './div[contains(text(), "$")]/preceding-sibling::div/text()')
    #     price_events.add_xpath('events', './div[contains(text(), "$")]/following-sibling::div/text()')

    @staticmethod
    def post_process(item):
        '''Add any additional data to an item after loading it'''
        if item.get('dates') is not None:
            dates = [datetime.datetime.strptime(date, '%m/%d/%Y') for date in item['dates']]
            prices = [int(price.lstrip('$').replace(',', '')) for price in item['prices']]
            item['price_history'] = sorted(list(zip(dates, prices, item['events'])), key=lambda x: x[0])

