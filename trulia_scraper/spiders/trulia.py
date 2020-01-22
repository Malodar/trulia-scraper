# -*- coding: utf-8 -*-
import os
import scrapy
import math
import datetime
import json
import re
from scrapy.linkextractors import LinkExtractor
from ..items import TruliaItem, TruliaItemLoader
from trulia_scraper.parsing import get_number_from_string
from scrapy.utils.conf import closest_scrapy_cfg
from w3lib.http import basic_auth_header


class TruliaSpider(scrapy.Spider):
    name = 'trulia'
    proxy = 'http://zproxy.lum-superproxy.io:22225'
    allowed_domains = ['trulia.com']
    custom_settings = {'FEED_URI': os.path.join(os.path.dirname(closest_scrapy_cfg()), 'data/data_for_sale_%(state)s_%(city)s_%(time)s.jl'),
                       'FEED_FORMAT': 'csv'}

    def __init__(self, state='IA', city='Waukee', zipcode='50263', *args, **kwargs):
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
                                 # meta={
                                 #     'proxy': self.proxy,
                                 # },
                                 )

    @staticmethod
    def get_number_of_pages_to_scrape(response):
        number_of_results = int(response.css("div[data-testid='pagination-caption']::text").extract_first().split()[2].replace(',', ''))
        return math.ceil(number_of_results/30)

    def parse_index_page(self, response):
        for link in self.le.extract_links(response):
            yield scrapy.Request(url=link.url,
                                 callback=self.parse_property_page,
                                 # meta={
                                 #     'proxy': self.proxy,
                                 # },
            )

    def parse_agents(self, response):
        item = response.meta['it']
        js = json.loads(response.body_as_unicode())
        try:
            item["agent_name"] = js['data']['homeDetailsByUrl']['provider']['agent']['name']
        except TypeError:
            item["agent_name"] = ''
        try:
            item["agent_phone_num"] = js['data']['homeDetailsByUrl']['provider']['agent']['phone']
        except TypeError:
            item["agent_phone_num"] = ''
        try:
            item["listing_agency"] = js['data']['homeDetailsByUrl']['provider']['broker']['name']
        except TypeError:
            item['listing_agency'] = ''
        except KeyError:
            print(js)
            item['listing_agency'] = ''
        try:
            item["listing_agency_phone"] = js['data']['homeDetailsByUrl']['provider']['broker']['phone']
        except KeyError:
            item["listing_agency_phone"] = ''
        except TypeError:
            item['listing_agency_phone'] = ''
        yield item

    def parse_property_page(self, response):
        item = TruliaItem()
        js = json.loads(response.css("script#__NEXT_DATA__::text").extract_first())
        home_details = js['props']['homeDetails']
        item['url'] = response.urljoin(home_details['url'])
        item['address'] = home_details['location']['homeFormattedAddress']
        item['latitude'] = home_details['location']['coordinates']['latitude']
        item['longitude'] = home_details['location']['coordinates']['longitude']
        item['city'] = home_details['location']['city']
        item['state'] = home_details['location']['stateCode']
        try:
            item['mls'] = re.search(r'MLS/Source ID: ([\d]+)', response.body_as_unicode()).group(1)
        except:
            item['mls'] = ''
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
        # price_history = home_details['priceHistory']
        # item['price_history'] = ",\n".join([f'{i["formattedDate"]} - {i["event"]} - {i["price"]["formattedPrice"].replace(",", "")}' for i in price_history])

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
        # self.post_process(item=item)
        csrf_token = js['props']['apolloHeaders']['x-csrf-token']
        # print(csrf_token)
        headers = {
            'Host': 'www.trulia.com',
            'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:71.0) Gecko/20100101 Firefox/71.0',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            # 'Referer': item['url'],
            'content-type': 'application/json',
            'x-csrf-token': csrf_token,
            'Origin': 'https://www.trulia.com',
            'Connection': 'keep-alive',
            # 'Cookie': 'tlftmusr=191021pzq01r59oll8iostonwlj4w204; _pxhd=f557f0a96fb23fb2fc4aedd6add35a4138e2934a81b183d2bdba8f4aa3694734:6361f181-f3ee-11e9-abf1-ebb4e3a02adb; zjs_anonymous_id=%22zga-a605d87a-415d-4b4c-b83f-48c3f09444b0%22; zjs_user_id=null; OptanonConsent=landingPath=NotLandingPage&datestamp=Thu+Nov+14+2019+14%3A32%3A22+GMT%2B0300+(Moscow+Standard+Time)&version=4.7.0&EU=false&groups=0_165083%3A1%2C1%3A1%2C3%3A1%2C0_165085%3A1%2C0_165087%3A1%2C2%3A1%2C4%3A1%2C0_165088%3A1%2C0_165089%3A1%2C0_165090%3A1%2C0_165091%3A1%2C0_165092%3A1%2C0_175811%3A1%2C0_175812%3A1%2C0_175813%3A1%2C0_175814%3A1%2C0_175815%3A1%2C0_175816%3A1%2C0_175817%3A1%2C0_175818%3A1%2C0_175819%3A1%2C0_175820%3A1%2C0_175821%3A1%2C0_175822%3A1%2C0_175823%3A1%2C0_175824%3A1%2C0_175825%3A1%2C0_175826%3A1%2C0_175827%3A1%2C0_175828%3A1%2C0_168400%3A1%2C0_175810%3A1%2C0_168401%3A1%2C0_165084%3A1&AwaitingReconsent=false; uex=1; utk=22f79aabbf8063226efd218b9860f50a6fa5d8a75a5986f720c626e64748839d; tlh=f30OBltRdwI%3D; stpa=4b1d052bc1efe333eed3d47cc8931dffa6e2949bec0079b78a9bc30ddc477ac5; stpr=1020a60b60dc97b348bc994bdc49d3a1b0cbc7237a33cf7a36c6cc4f9b30e1b0; OptanonConsent=landingPath=NotLandingPage&datestamp=Thu+Dec+26+2019+14%3A04%3A11+GMT%2B0300+(Moscow+Standard+Time)&version=5.8.0&EU=false&groups=1%3A1%2C3%3A1%2C4%3A1%2C0_234869%3A1%2C0_234866%3A1%2C0_234867%3A1%2C0_234868%3A1%2C0_240782%3A1%2C0_240783%3A1%2C0_240780%3A1%2C0_234871%3A1%2C0_240781%3A1%2C0_234872%3A1%2C0_234873%3A1%2C0_234874%3A1%2C0_234875%3A1%2C0_234876%3A1%2C0_234877%3A1&AwaitingReconsent=false; fvstts=20191215; G_ENABLED_IDPS=google; uid=59651077; uem=kunitsyn-a-v%40yandex.ru; lgi=54513eaea1c5a9f70a32743cc03dcf8f; tr_prod=%7B%22uem%22%3A%22kunitsyn-a-v%40yandex.ru%22%2C%22lgi%22%3A%22490541fdbde4eec298074bf78d912f35%22%2C%22msqd%22%3A0%2C%22umsqd%22%3A%22%22%2C%22gmsqd%22%3A%5B%5D%2C%22usrid%22%3A%2259651077%22%7D; QSI_S_ZN_aVrRbuAaSuA7FBz=v:0:0; PHPSESSID=fqfefiren0i2d8rtnp93hndq30; SERVERID=webfe333|XfotP; _csrfSecret=QffeFl5gaA1rS-3tV4GHq7p-; csrft=M%2Bb8zTpZ42xSLEj5mOq0B6q16z40r0SQK2%2FcTn708NI%3D; tabc=%7B%221148%22%3A%22a%22%2C%221177%22%3A%22a%22%2C%221181%22%3A%22c%22%2C%221182%22%3A%22a%22%2C%221189%22%3A%22a%22%2C%221193%22%3A%22a%22%7D',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
            'TE': 'Trailers'
        }
        # print('ITEM:', item)
        yield scrapy.Request(url='https://www.trulia.com/graphql?opname=WEB_homeDetailsClientLeadFormLookUp',
                             method='POST',
                             body=json.dumps({"operationName":"WEB_homeDetailsClientLeadFormLookUp",
                                                  "variables":{"heroImageFallbacks":["STREET_VIEW", "SATELLITE_VIEW"],
                                                               "url":home_details['url'],
                                                               "query":'null',
                                                               "searchEncodedHash":'null',
                                                               "searchType":'null',
                                                               "isBot":'false',
                                                               "isSPA":'false',
                                                               "isScheduleATourEnabled":'true'},
                                                  "query":"query WEB_homeDetailsClientLeadFormLookUp($url: String!, $isScheduleATourEnabled: Boolean!) {\n  homeDetailsByUrl(url: $url) {\n    url\n    ...LeadFormFragment\n    ...HomeDetailsListingProviderFragment\n    __typename\n  }\n}\n\nfragment Agent on LEADFORM_Contact {\n  __typename\n  displayName\n  callPhoneNumber\n  textMessagePhoneNumber\n  ... on LEADFORM_AgentContact {\n    agentType\n    agentId\n    agentRating {\n      averageValue\n      maxValue\n      __typename\n    }\n    numberOfReviews\n    numberOfRecentSales\n    role\n    hasPAL\n    profileURL(pathOnly: false)\n    largeImageUrl\n    profileImageURL\n    broker {\n      name\n      phoneNumber\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment LeadFormContactFragment on LEADFORM_ContactLayout {\n  callToActionDisplay(appendOneClick: true) {\n    callToActionDisplayLabel\n    supportsCancellableSubmission\n    callToActionType\n    __typename\n  }\n  contactList {\n    ... on LEADFORM_AgentContactList {\n      allowsSelection\n      footer {\n        markdown\n        __typename\n      }\n      __typename\n    }\n    __typename\n    contacts {\n      ...Agent\n      __typename\n    }\n    primaryContactPhoneNumber\n  }\n  additionalComponents {\n    componentId\n    displayLabel\n    __typename\n    ... on LEADFORM_CheckboxComponent {\n      isChecked\n      displayLabel\n      displayLabelSelected\n      displayLabelUnselected\n      __typename\n    }\n  }\n  formComponents {\n    __typename\n    componentId\n    displayLabel\n    ... on LEADFORM_LongTextInputComponent {\n      optional\n      defaultValue\n      validationRegex\n      validationErrorMessage\n      placeholder\n      __typename\n    }\n    ... on LEADFORM_ShortTextInputComponent {\n      optional\n      defaultValue\n      validationRegex\n      validationErrorMessage\n      placeholder\n      __typename\n    }\n    ... on LEADFORM_OptionGroupComponent {\n      options {\n        displayLabel\n        value\n        __typename\n      }\n      optional\n      __typename\n    }\n    ... on LEADFORM_CheckboxComponent {\n      isChecked\n      displayLabel\n      componentId\n      tooltipText\n      descriptionText\n      __typename\n    }\n    ... on LEADFORM_SingleSelectOptionGroupComponent {\n      __typename\n      componentId\n      disclaimerInformation {\n        displayLabel\n        detailsLabel\n        __typename\n      }\n    }\n  }\n  disclaimers {\n    copy\n    links {\n      target\n      ... on LEADFORM_DisclaimerLinkURL {\n        destinationURL\n        __typename\n      }\n      ... on LEADFORM_DisclaimerLinkTooltip {\n        body\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  lenders {\n    imageURL\n    displayName\n    formattedPhoneNumber\n    formattedNMLSLicense\n    __typename\n  }\n  prequalifier {\n    cta {\n      displayTitle\n      displayMessage\n      callToActionLabel\n      __typename\n    }\n    confirmation {\n      displayTitle\n      displayMessage\n      affirmationLabel\n      cancellationLabel\n      ... on LEADFORM_SubsidizedIncomePrequalifierConfirmation {\n        subsidizedIncomeOptions {\n          formattedIncome\n          totalResidents\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment ScheduleTourFragment on HOME_Property {\n  scheduleATourLeadForm(onScheduleTourEnabled: $isScheduleATourEnabled) {\n    __typename\n    formComponents {\n      componentId\n      displayLabel\n      ... on LEADFORM_ScheduleSelectComponent {\n        options {\n          header\n          footer\n          content\n          timeOptions {\n            label\n            value\n            __typename\n          }\n          __typename\n        }\n        optional\n        __typename\n      }\n      ... on LEADFORM_ShortTextInputComponent {\n        optional\n        defaultValue\n        validationRegex\n        validationErrorMessage\n        placeholder\n        __typename\n      }\n      __typename\n    }\n    displayHeader\n    tracking {\n      pixelURL\n      transactionID\n      __typename\n    }\n    ... on LEADFORM_TourScheduleLayout {\n      callToActionDisplay {\n        callToActionDisplayLabel\n        __typename\n      }\n      __typename\n    }\n    disclaimers {\n      copy\n      links {\n        target\n        ... on LEADFORM_DisclaimerLinkURL {\n          destinationURL\n          __typename\n        }\n        ... on LEADFORM_DisclaimerLinkTooltip {\n          body\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n  }\n  __typename\n}\n\nfragment LeadFormFragment on HOME_Details {\n  ...ScheduleTourFragment\n  leadForm(onScheduleTourEnabled: $isScheduleATourEnabled) {\n    __typename\n    ... on LEADFORM_ButtonLayout {\n      description\n      formComponents {\n        componentId\n        displayLabel\n        actionType\n        actionURL\n        __typename\n      }\n      __typename\n    }\n    ... on LEADFORM_PartnerLayout {\n      description\n      imageURL\n      formComponents {\n        componentId\n        displayLabel\n        actionType\n        actionURL\n        __typename\n      }\n      __typename\n    }\n    ...LeadFormContactFragment\n    tracking {\n      pixelURL\n      transactionID\n      __typename\n    }\n  }\n  __typename\n}\n\nfragment HomeDetailsListingProviderFragment on HOME_Details {\n  provider(onScheduleTourEnabled: $isScheduleATourEnabled) {\n    providerHeader\n    providerTitle\n    disclaimer {\n      name\n      value\n      __typename\n    }\n    agent {\n      name\n      phone\n      imageUrl\n      listingAgentId\n      isAssociatedWithBroker\n      __typename\n    }\n    broker {\n      name\n      phone\n      email\n      logoUrl\n      url\n      __typename\n    }\n    mls {\n      name\n      logoUrl\n      __typename\n    }\n    description\n    youtubeUrl\n    __typename\n  }\n  __typename\n}\n"
                                                  }),
                             headers=headers,
                             callback=self.parse_agents,
                             meta={'it': item},
                             )
        # return item

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
