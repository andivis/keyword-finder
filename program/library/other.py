import sys
import os
import logging
import json
import random
import re
import datetime

from collections import OrderedDict

# pip packages
import lxml.html as lh

if '--debug' in sys.argv:
    import helpers as helpers
    from api import Api
    from website import Website
    from database import Database

    from helpers import get
else:
    from . import helpers
    from .api import Api
    from .website import Website
    from .database import Database
    
    from .helpers import get

class ContactUploader:
    def upload(self, inputRow, newItems):
        destinations = get(inputRow, 'destinations').split()

        # add default destinations
        optionNames = [
            'googleSheetsUrl',
            'activeCampaignListUrl',
            'zapierWebhookUrl'
        ]

        for optionName in optionNames:
            row = self.database.getFirst('option', '*', f"userId = {self.options['userId']} and name = '{optionName}'")

            value = get(row, 'value')

            if value and not value in destinations:
                destinations.append(value)

        fields = ['date', 'site', 'keyword', 'name', 'email', 'phone', 'website', 'headline', 'summary', 'location', 'country', 'job title', 'company', 'industry', 'positions', 'school', 'field of study', 'id', 'linkedin url', 'twitter url', 'facebook url', 'instagram url', 'youtube url', 'google maps url']

        hasMasterSheet = False

        masterSheetId = helpers.findBetween(get(self.options, 'masterGoogleSheet'), '/spreadsheets/d/', '/')
        masterSheetUrl = get(self.options, 'masterGoogleSheet')

        if '--debug' in sys.argv:
            masterSheetId = helpers.findBetween(get(self.options, 'debugMasterGoogleSheet'), '/spreadsheets/d/', '/')
            masterSheetUrl = get(self.options, 'debugMasterGoogleSheet')

        for destination in destinations:
            if masterSheetId in destination:
                hasMasterSheet = True
                break

        for destination in destinations:
            if 'https://docs.google.com/spreadsheets/' in destination:
                self.sendToGoogleSheet(inputRow, newItems, fields, destination, True, masterSheetId)
            elif '.activehosted.com/' in destination:
                self.sendToEmailProvider(inputRow, newItems, destination)
            elif '.zapier.com/' in destination:
                self.sendToZapier(inputRow, newItems, destination)

        if not hasMasterSheet:
            self.sendToGoogleSheet(inputRow, newItems, fields, masterSheetUrl, False)

    def sendToGoogleSheet(self, item, newItems, fields, destination, showMessage, masterSheetId=None):
        if not '/spreadsheets/d/' in destination:
            self.log.error(f'{destination} is not a Google sheet URL')
            return

        contacts = []

        sheetId = helpers.findBetween(destination, '/spreadsheets/d/', '/')

        tabId = ''

        fieldsToUse = fields.copy()
        sourceEmail = ''

        # master sheet?
        if not showMessage or sheetId == masterSheetId:
            row = self.database.getFirst('user', 'emailAddress', f"id = {self.options['userId']}")
            sourceEmail = get(row, 'emailAddress')
            fieldsToUse.append('source account')

        if 'gid=' in destination:
            tabId = helpers.findBetween(destination, 'gid=', '&')

        if not tabId or tabId == '0':
            tabId = ''

        if not sheetId:
            self.log.error(f'Can\'t get sheet ID from {destination}')
            return

        for newItem in newItems:
            # change date format
            date = datetime.datetime.strptime(get(newItem, 'gmDate'), '%Y-%m-%d %H:%M:%S.%f')

            dateString = helpers.localTimeString(date, self.options['defaultTimezone'])
            
            values = [
                ('date', dateString),
                ('site', item.get('site', '')),
                ('keyword', item.get('keyword', ''))
            ]

            for field in fieldsToUse[3:]:
                pair = (field, newItem.get(field, ''))
                values.append(pair)

            if sourceEmail:
                values.append(('source account', sourceEmail))
            
            contact = OrderedDict(values)
            contacts.append(contact)

        toSend = {
            'sheetId': sheetId,
            'tabId': tabId,
            'columns': fieldsToUse,
            'contacts': contacts
        }
        
        api = Api('', self.options)
        
        url = 'https://script.google.com/macros/s/AKfycbzoHiJ15SJGqXxFyS3u99SBBOVuOJxmdccfqeAUmDWn6X5cle4/exec'

        if showMessage:        
            self.log.info(f'Sending to Google sheet. Sheet ID: {sheetId}.')
        else:
            self.log.debug(f'Sending to Google sheet. Sheet ID: {sheetId}.')
        
        self.log.debug(f'Request body: ' + json.dumps(toSend))
        
        response = api.post(url, json.dumps(toSend))

        if response.get('status', '') == 'success':
            if showMessage:
                self.log.info('Success')
            else:
                self.log.debug('Success')
        else:
            inputFile = self.options['inputFile']
            error = response.get('message', '')
            self.log.error(f'Something went wrong: {error}')
            self.log.error(f'Make sure your sheet id in {inputFile} is correct')
            self.log.error('You probably need to share the spreadsheet first. Open the spreadsheet, click "Share", "Get shareable link", "Anyone with link can edit". Then try again.')

    def sendToEmailProvider(self, item, newItems, destination, toMaster=False):
        if not toMaster:
            self.log.info('Sending results to email provider')
        else:
            self.log.debug('Sending results to email provider')
        
        listId = helpers.findBetween(destination, 'listid=', '&')

        if not listId:
            self.log.error(f'Can\'t get list ID from {destination}')
            return

        isCompany = False

        if get(item, 'site') == 'maps.google.com' or get(item, 'options') == 'companies':
            isCompany = True

        for newItem in newItems:
            email = newItem.get('email', '')

            if not email:
                if not toMaster:
                    self.log.info('Not uploading to email provider. Email is blank.')
                continue

            if '.activehosted.com/' in destination:
                if toMaster:
                    from program.other.active_campaign import ActiveCampaign
                    masterActiveCampaign = ActiveCampaign(self.options, self.credentials, self.database, True)
                    masterActiveCampaign.addContact(newItem, listId, isCompany, False)
                else:
                    self.log.info(f'Sending to ActiveCampaign: {email}. List ID: {listId}.')
                    self.activeCampaign.addContact(newItem, listId, isCompany)

    def sendToHubspot(self, item, newItems, toMaster=False):
        if not toMaster:
            self.log.info('Sending results to HubSpot')
        else:
            self.log.debug('Sending results to HubSpot')
        
        isCompany = False

        if get(item, 'site') == 'maps.google.com' or get(item, 'options') == 'companies':
            isCompany = True

        tag = self.options['productName'] + 'AllUsers'
        
        for newItem in newItems:
            self.hubspot.addContact(newItem, isCompany, tag, not toMaster)

    def sendToZapier(self, item, newItems, destination):
        self.log.info(f'Sending to Zapier: {destination}')

        toSend = []

        zapierApi = Api('', self.options)

        for newItem in newItems:
            email = newItem.get('email', '')

            if not email:
                self.log.info('Not uploading to Zapier. Email is blank.')
                continue

            itemToSend = {
                "site": get(item, 'site'),
                "keyword": get(item, 'keyword'),
                "id": get(newItem, 'id'),
                "full_name": self.contactHelpers.getName(newItem),
                "first_name": self.contactHelpers.getFirstNameFromItem(newItem),
                "last_name": self.contactHelpers.getLastNameFromItem(newItem),
                "email": get(newItem, 'email'),
                "phone": get(newItem, 'phone'),
                "website": get(newItem, 'website')
            }

            toSend.append(itemToSend)

        if not toSend:
            return
        
        response = zapierApi.post(destination, json.dumps(toSend))

        if get(response, 'status') == 'success':
            self.log.info('Success')
        else:
            self.log.error('Something went wrong when sending results to Zapier')

    def __init__(self, options, credentials, database):
        self.options = options
        self.credentials = credentials
        self.log = logging.getLogger(get(options, 'loggerName'))
        self.database = database
        self.contactHelpers = ContactHelpers(self.options)
        
        from program.other.active_campaign import ActiveCampaign        
        self.activeCampaign = ActiveCampaign(self.options, self.credentials, self.database)
        
        from program.other.hubspot import Hubspot
        self.hubspot = Hubspot(self.options, self.credentials, self.database)

class ContactHelpers:
    def addContactInformationFromDomain(self, company, domain, google):
        domainToUse = helpers.getDomainName(domain)

        if not domainToUse:
            return company

        url = google.search(f'site:{domainToUse} contact', 1)

        # check if it contains contact information
        if not url or url == 'no results':
            return company

        contactInformation = self.getContactInformation(company, url)

        company = helpers.mergeDictionaries(company, contactInformation)

        return company

    def getContactInformation(self, company, url, baseXpath=None, moreXpaths=[]):
        results = {}

        api = Api('', self.options)
        html = api.getPlain(url)

        if not html:
            return results

        document = lh.fromstring(html)

        xpaths = [
            ["//a[starts-with(@href, 'mailto:')]", 'href', 'email'],
            ["//a[starts-with(@href, 'tel:')]", 'href', 'phone'],
            ["//a[contains(@href, 'facebook.com/')]", 'href', 'facebook'],
            ["//a[contains(@href, 'twitter.com/')]", 'href', 'twitter'],
            ["//a[contains(@href, 'instagram.com/')]", 'href', 'instagram'],
            ["//a[contains(@href, 'youtube.com/')]", 'href', 'youtube']
        ]

        website = Website({})

        document = website.removeTags(document)

        xpaths += moreXpaths

        for xpath in xpaths:
            if get(company, xpath[2]):
                continue    

            baseElement = document

            if baseXpath:
                baseElement = website.getXpathInElement(document, baseXpath, True)

                if not baseElement:
                    self.log.debug(f'Skipping. Did not find an element matching {baseXpath} on {url}')
                    continue

            elements = website.getXpathInElement(document, xpath[0], False)

            attribute = xpath[1]

            for element in elements:
                value = ''

                if not attribute:
                    value = element.text_content()
                else:
                    value = element.attrib[attribute]

                if value:
                    keyName = xpath[2]

                    if xpath[2] == 'email' or xpath[2] == 'phone':
                        value = helpers.findBetween(value, ':', '?')
                        # in case there are multiple emails
                        value = helpers.findBetween(value, '', ',')
                        value = value.lower()

                        if xpath[2] == 'email':
                            value = self.getFirstEmail(value)
                            
                            if not self.isEmail(value):
                                continue
                        elif xpath[2] == 'phone':
                            value = self.getPhoneNumberOnly(value);

                            if not self.isPhoneNumber(value):
                                continue
                    else:
                        avoidUrls = ['/sharer.php?', 'twitter.com/share?', 'linkedin.com/shareArticle?']

                        if helpers.substringIsInList(avoidUrls, value):
                            self.log.debug(f'Skipping. {value} is in avoidUrls.')
                            continue

                        # for links that use whatever the current page's protocol is
                        if value.startswith('//'):
                            value = helpers.findBetween(url, '', '//') + value

                        from .sites.site import SiteHelpers
                        value = SiteHelpers.getProfileUrl(xpath[2], value)
                        value = self.formattedUrl(value)

                        keyName += ' url'

                    results[keyName] = value

                    self.log.debug(f'Found {keyName} on {url}: {value}')

                    # just take first phone, email, etc.
                    break

        baseXpathForPlainText = './/body'

        if baseXpath:
            baseXpathForPlainText = baseXpath

        plainText = website.getXpath('', baseXpathForPlainText, True, None, document)

        if not get(company, 'email') and not get(results, 'email'):
            results['email'] = self.getFirstEmail(plainText)

        if not get(company, 'phone') and not get(results, 'phone'):
            results['phone'] = self.getFirstPhoneNumber(url, plainText)

        return results

    def getContactInformationInPlainText(self, url, text, result):
        if not get(result, 'email'):
            result['email'] = self.getFirstEmail(text)

        if not get(result, 'phone'):
            result['phone'] = self.getFirstPhoneNumber(url, text)

        if not get(result, 'website'):
            website = self.getUrlsInText(url, text, firstOnly=True)
            
            if website:
                result['website'] = website

        return result

    def getUrlsInText(self, url, plainText, firstOnly=False):
        results = []

        regex = r'(http(s)?:\/\/.)?(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)'

        for line in plainText.splitlines():
            for match in re.finditer(regex, line):
                match = match.group()
                
                if self.isEmail(match):
                    continue

                match = self.formattedUrl(match)
                
                self.log.debug(f'Found website on {url}: {match}')

                if firstOnly:
                    return match

                results.append(match)

        return results

    def formattedUrl(self, url):
        if not url:
            return ''

        protocol = helpers.findBetween(url, '', '://', strict=True)
        domain = helpers.findBetween(url, '://', '/')
        path = helpers.findBetween(url, f'{domain}', '', strict=True)

        if protocol:
            protocol += '://'

        result = protocol.lower() + domain.lower() + path

        return result

    def getFirstName(self, fullName):
        # this leaves out middle names and initials
        return helpers.findBetween(fullName, '', ' ')

    def getLastName(self, fullName):
        return helpers.getLastAfterSplit(fullName, ' ', minimumFieldCount=2)

    def getName(self, item):
        result = item.get('name', '')

        # prefer these fields if available
        if get(item, 'firstName'):
            result = get(item, 'firstName') + ' ' + get(item, 'lastName')
        elif get(item, 'first name'):
            result = get(item, 'first name') + ' ' + get(item, 'last name')

        return result

    def getFirstNameFromItem(self, item):
        result = self.getFirstName(item.get('name', ''))

        # prefer these fields if available
        if get(item, 'firstName'):
            result = get(item, 'firstName')
        elif get(item, 'first name'):
            result = get(item, 'first name')

        return result

    def getLastNameFromItem(self, item):
        result = self.getLastName(item.get('name', ''))

        # prefer these fields if available
        if get(item, 'lastName'):
            result = get(item, 'lastName')
        elif get(item, 'last name'):
            result = get(item, 'last name')

        return result

    def getFirstPhoneNumber(self, url, plainText):
        result = ''

        signsOfCorruptHtml = [
            '<span',
            '<svg',
            '<div'
        ]

        if helpers.substringIsInList(signsOfCorruptHtml, plainText):
            self.log.debug(f'Skipping. {url} contains signsOfCorruptHtml.')
            return result

        # must start with + or a digit. otherwise the end of the phone number can get cut off because of wrong leading characters.
        regex = r'[\+\d]+[\d\s\-\*\.\(\)]{6,22}'

        for line in plainText.splitlines():
            matches = re.findall(regex, line)

            # because might match strings that are not phone numbers. so try all matches.
            for match in matches:
                if not self.isPhoneNumber(match):
                    continue

                result = self.getPhoneNumberOnly(match)
                self.log.debug(f'Found phone number on {url}: {result}')
                return result

        return result

    def isEmail(self, string):
        result = False

        if not string:
            return result

        if not '@' in string:
            return result

        if '/' in string:
            return result

        return True

    def isPhoneNumber(self, string):
        result = False

        if ' - ' in string:
            return result

        numbers = helpers.numbersOnly(string)

        if numbers.startswith('000'):
            return result

        minimumDigits = self.options.get('minimumDigitsInPhoneNumber', 10)
        maximumDigits = self.options.get('minimumDigitsInPhoneNumber', 12)

        if len(numbers) >= minimumDigits and len(numbers) <= maximumDigits:
            result = True

        return result

    def getPhoneNumberOnly(self, string):
        result = string

        result = result.replace('/', '')
        result = result.replace('\\', '')
        result = result.replace('(', '')
        result = result.replace(')', '')
        result = result.replace('*', '-')
        result = result.replace('.', '-')
        result = helpers.squeeze(result, ['-'])
        result = helpers.squeezeWhitespace(result)
        result = result.strip()
        result = result.strip('-')

        return result

    def getFirstEmail(self, plainText):
        result = ''

        regex = r'(([^<>()\[\]\\.\,\*;:\s@\|"]+(\.[^<>()\[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))'

        for line in plainText.splitlines():
            match = re.search(regex, line)

            if not match:
                continue

            result = match.group()
            result = result.lower()

            break

        if not self.isEmail(plainText):
            return

        return result

    def hasContactInformation(self, contact):
        if not get(contact, 'email') and not get(contact, 'phone'):
            self.log.debug(f'Storing to database only. No email or phone number for {get(contact, "id")}.')
            return False

        return True

    def getFuzzyVersion(self, s):
        result = s.lower()
        result = result.strip()
        return helpers.squeezeWhitespace(result)

    def getBasicCompanyName(self, s):
        import re

        # description or extraneous information usually comes after
        s = helpers.findBetween(s, '|', '')
        s = helpers.findBetween(s, ' - ', '')
        s = helpers.findBetween(s, ',', '')
        s = helpers.findBetween(s, '(', '')

        s = s.replace('-', ' ')
        s = s.replace('&', ' ')

        s = helpers.lettersNumbersAndSpacesOnly(s)
        s = self.getFuzzyVersion(s)

        stringsToIgnore = [
            'limited',
            'ltd',
            'llc',
            'inc',
            'pty',
            'pl',
            'co',
            'corp'
            'incorporated'
        ]

        for string in stringsToIgnore:
            # word with space before and after
            s = re.sub(f' {string} ', ' ', s)
            # ends in the string
            s = re.sub(f' {string}$', '', s)

        s = self.getFuzzyVersion(s)

        return s

    def toDatabase(self, inputRow, newItem, database):
        if not newItem:
            return

        jsonColumn = newItem

        destinations = inputRow.get('destinations', '')

        if inputRow.get('mode', '') == 'contact information':
            # so it doesn't count as a result later
            if not self.hasContactInformation(newItem):
                destinations = ''

        itemToStore = {
            'userId': self.options['userId'],
            'site': inputRow.get('site', ''),
            'mode': inputRow.get('mode', ''),
            'keyword': inputRow.get('keyword', ''),
            'id': newItem.get('id', ''),
            'name': self.getName(newItem),
            'email': newItem.get('email', ''),
            'phone': newItem.get('phone', ''),
            'website': newItem.get('website', ''),
            'destinations': destinations,
            'gmDate': str(datetime.datetime.utcnow()),
            'json': json.dumps(jsonColumn)
        }

        database.insert('result', itemToStore)

    def sharedResultToDatabase(self, inputRow, newItem, type, keys, database):
        if not newItem:
            return

        jsonColumn = newItem

        itemToStore = {
            'site': inputRow.get('site', ''),
            'id': newItem.get('id', ''),
            'otherId': newItem.get(get(keys, 'otherId'), ''),
            'type': type,
            'keyword': inputRow.get('keyword', ''),
            'name': self.getName(newItem),
            'email': newItem.get('email', ''),
            'phone': newItem.get('phone', ''),
            'website': newItem.get('website', ''),
            'location': newItem.get('location', ''),
            'country': newItem.get('country', ''),
            'companyId': newItem.get(get(keys, 'companyId'), ''),
            'companyOtherId': newItem.get(get(keys, 'companyUrn'), ''),
            'companyName': newItem.get(get(keys, 'companyName'), ''),
            'companyLinkedInUrl': newItem.get(get(keys, 'companyLinkedInUrl'), ''),
            'companyWebsite': newItem.get('companyWebsite', ''),
            'linkedinUrl': newItem.get('linkedin url', ''),
            'twitterUrl': newItem.get('twitter url', ''),
            'facebookUrl': newItem.get('facebook url', ''),
            'instagramUrl': newItem.get('instagram url', ''),
            'youtubeUrl': newItem.get('youtube url', ''),
            'googleMapsUrl': newItem.get('google maps url', ''),
            'gmDate': str(datetime.datetime.utcnow()),
            'json': json.dumps(jsonColumn)
        }

        database.insert('sharedResult', itemToStore)

    def newResultsToday(self, inputRow, database, timezone=0, numberOfDays=None, fromGmDate=None):
        import datetime

        now = datetime.datetime.utcnow() + datetime.timedelta(hours=int(timezone))

        startOfDay = now.replace(hour=0, minute=0, second=0, microsecond=0)
        startOfDay = startOfDay - datetime.timedelta(hours=timezone)

        if fromGmDate:
            startOfDay = fromGmDate
        elif numberOfDays == -1:
            startOfDay = ''
        elif numberOfDays:
            startOfDay = now - datetime.timedelta(hours=24 * numberOfDays)
        
        filter = ''

        if inputRow:
            filter = f"and site = '{get(inputRow, 'site')}' and mode = '{get(inputRow, 'mode')}'"

            if get(inputRow, 'keyword'):
                filter += f" and keyword = '{get(inputRow, 'keyword')}'"

        newResultsToday = database.getFirst('result', 'count(*)', f"userId = {self.options['userId']} {filter} and (length(email) > 0 or length(phone) > 0 or length(sentMessage) > 0) and gmDate >= '{startOfDay}'")
        newResultsToday = get(newResultsToday, 'count(*)')

        return int(newResultsToday)      
    
    def enoughForOneDay(self, options, inputRow, database, timezone=0):
        newResultsToday = 0

        user = database.getFirst('user', '*', f"id = {self.options['userId']}")
        jsonColumn = json.loads(get(user, 'json'))

        if get(user, 'status') == 'trialing':
            # all actions and all time
            newResultsToday = self.newResultsToday(inputRow, database, timezone, True, True)
        else:
            newResultsToday = self.newResultsToday(inputRow, database, timezone)

        maximumNewResultsPerCalendarDay = inputRow.get('maximumNewResultsPerCalendarDay', options['maximumNewResultsPerCalendarDay'])
        maximumNewResultsPerCalendarDay = int(maximumNewResultsPerCalendarDay)

        # check account limit
        if get(user, 'status') == 'trialing':
            maximumFreeResults = int(get(options, 'maximumResultsFreeUsers'))

            if get(jsonColumn, 'freeLeads') != '':
                maximumFreeResults = get(jsonColumn, 'freeLeads')

            if maximumFreeResults == 0 or newResultsToday >= maximumFreeResults:
                self.log.error(f'You used all your free leads. Click the upgrade link above to continue using {self.options["productName"]}.')

            maximumNewResultsPerCalendarDay = maximumFreeResults
        elif get(user, 'type') == 'regular' and get(jsonColumn, 'mode') == 'beta':
            newResultsTodayAcrossActions = self.newResultsToday(inputRow, database, timezone, True)
        
            maximumNewResultsPerDayForBetaUsers = int(get(self.options, 'maximumNewResultsPerDayForBetaUsers'))

            if maximumNewResultsPerDayForBetaUsers and newResultsTodayAcrossActions >= maximumNewResultsPerDayForBetaUsers:
                self.log.info(f'Reached limit of {maximumNewResultsPerDayForBetaUsers} new results across all {self.options["actionNamePlural"]} for today. You can continue tomorrow.')
                return True

            if maximumNewResultsPerCalendarDay > 100:
                self.log.debug(f'Limiting maximumNewResultsPerCalendarDay to 100')
                maximumNewResultsPerCalendarDay = 100
        
        if newResultsToday < maximumNewResultsPerCalendarDay:
            return False

        self.log.info(f'Reached limit of {maximumNewResultsPerCalendarDay} new results for today.')

        return True

    def getMaximum(self, options, inputRow, resultType):
        maximum = inputRow.get(resultType, options[resultType])

        return int(maximum)
        
    def enoughResults(self, options, inputRow, newItems, resultType):
        result = False
        
        maximum = self.getMaximum(options, inputRow, resultType)

        if resultType == 'maximumNewResults':
            self.log.debug(f'New results: {len(newItems)} of {int(maximum)}')

        if not maximum:
            maximum = 25
        
        if len(newItems) >= int(maximum):
            typeString = ''

            if resultType == 'maximumNewResults':
                typeString = 'new'
            else:
                typeString = 'search'

            self.log.info(f'Reached the maximum of {maximum} {typeString} results.')
            result = True

        return result

    def __init__(self, options=None):
        self.options = options
        self.log = logging.getLogger(get(options, 'loggerName'))

class Internet:
    def getProxiesFromApi(self):
        result = None

        if self.proxyProvider == 'proxy bonanza':
            result = self.getProxiesFromProxyBonanzaApi()
        elif self.proxyProvider == 'my private proxy':
            result = self.getProxiesFromMyPrivateProxyApi()
        elif self.proxyProvider == 'smartproxy':
            externalApi = Api('', self.options)
            result = externalApi.getPlain(self.proxyListUrl)
            result = result.splitlines()

        return result

    def getProxiesFromProxyBonanzaApi(self):
        result = None

        externalApi = Api('', self.options)
        apiKey = externalApi.getPlain(self.proxyListUrl)

        if not apiKey:
            return result

        if ',' in apiKey:
            return self.getFromCsv(apiKey)

        ipsToKeep = externalApi.getPlain(self.proxyListUrl + '-allowed')
        ipsToKeep = ipsToKeep.splitlines()

        api = Api('https://api.proxybonanza.com')

        api.headers = {
            'Authorization': apiKey
        }

        allowedIps = []
        allowedIpIds = {}
        packages = api.get(f'/v1/userpackages.json')
        packageId = None

        for package in get(packages, 'data'):
            packageId = get(package, 'id')
            userName = get(package, 'login')
            password = get(package, 'password')

            packageDetails = api.get(f'/v1/userpackages/{packageId}.json')

            for allowedIp in helpers.getNested(packageDetails, ['data', 'authips']):
                ip = get(allowedIp, 'ip')

                if not ip in allowedIps:
                    allowedIps.append(ip)

                id = get(allowedIp, 'id')

                allowedIpIds[id] = ip

            for ipPack in helpers.getNested(packageDetails, ['data', 'ippacks']):
                newItem = {
                    'url': ipPack.get('ip', ''),
                    'port': ipPack.get('port_http', ''),
                    'username': userName,
                    'password': password
                }

                if not result:
                    result = []

                result.append(newItem)

        ipInfoApi = Api('', self.options)

        currentIp = ipInfoApi.get('https://ipinfo.io/json')

        if not currentIp or not currentIp.get('ip', ''):
            self.log.debug('Can\'t find current ip address')
            return result

        currentIp = currentIp.get('ip', '')
        
        # check if it's already allowed
        if not currentIp in allowedIps and not '--debug' in sys.argv:
            maximumAllowedIps = 15
            
            # list if full?
            if len(allowedIps) >= maximumAllowedIps:
                toDelete = None

                for id, ip in allowedIpIds.items():
                    if not ip in ipsToKeep:
                        toDelete = id
                        break

                # delete old ip
                if toDelete:
                    response = api.get(f'/v1/authips/{toDelete}.json', requestType='DELETE')

                    if not get(response, 'success'):
                        self.log.debug('Failed to delete allowed ip address')

            # add new one
            body = {
                'ip': currentIp,
                'userpackage_id': packageId
            }

            response = api.post(f'/v1/authips.json', body)

            if not get(response, 'success'):
                self.log.debug('Failed to add allowed ip address')

        return result

    def getProxiesFromMyPrivateProxyApi(self):
        result = None

        externalApi = Api('', self.options)
        apiKey = externalApi.getPlain(self.proxyListUrl)

        if not apiKey:
            return result

        if ',' in apiKey:
            return self.getFromCsv(apiKey)

        api = Api('https://api.myprivateproxy.net')

        # get allowed ip's
        allowedIps = api.get(f'/v1/fetchAuthIP/{apiKey}')

        if not allowedIps:
            return result

        ipInfoApi = Api('', self.options)

        currentIp = ipInfoApi.get('https://ipinfo.io/json')

        if not currentIp or not currentIp.get('ip', ''):
            self.log.debug('Can\'t find current ip address')
            return result

        currentIp = currentIp.get('ip', '')

        # check if it's already allowed
        if not currentIp in allowedIps and not '--debug' in sys.argv:
            toKeep = 3
            newAllowedIps = allowedIps[0:toKeep]
            newAllowedIps.append(currentIp)

            # add current ip to allowed ip's
            response = api.post(f'/v1/updateAuthIP/{apiKey}', json.dumps(newAllowedIps))

            if response.get('result', '') != 'Success':
                self.log.debug('Failed to update allowed ip addresses')

        response = api.get(f'/v1/fetchProxies/json/full/{apiKey}')

        if not response:
            return result

        result = []

        for item in response:
            newItem = {
                'url': item.get('proxy_ip', ''),
                'port': item.get('proxy_port', ''),
                'username': item.get('username', ''),
                'password': item.get('password', ''),
            }

            result.append(newItem)

        return result

    def getFromCsv(self, csv):
        result = []

        for line in csv.splitlines():
            fields = line.split(',')

            if fields[0] == 'url':
                continue

            newItem = {
                'url': fields[0],
                'port': fields[1],
                'username': fields[2],
                'password': fields[3]
            }

            result.append(newItem)

        return result

    def getRandomProxy(self):
        if not self.proxies:
            if os.path.exists('user-data/proxies.csv'):
                self.proxies = helpers.getCsvFile('user-data/proxies.csv')
            elif self.proxyListUrl:            
                self.proxies = self.getProxiesFromApi()

            if not self.proxies:
                self.log.info('No proxies found')

        if not self.proxies:
            return None

        item = random.choice(self.proxies)

        if isinstance(item, dict):
            url = item.get('url', '')
            port = item.get('port', '')
            userName = item.get('username', '')
            password = item.get('password', '')

            proxy = f'http://{userName}:{password}@{url}:{port}'

            if not userName or not password:
                proxy = f'http://{url}:{port}'

            self.log.debug(f'Using proxy http://{url}:{port}')
        # plain string
        else:
            proxy = item
            self.log.debug('Using proxy ' + helpers.findBetween(proxy, '@', ''))

        proxies = {
            'http': proxy,
            'https': proxy
        }

        return proxies

    def __init__(self, options):
        self.options = options
        self.log = logging.getLogger(get(options, 'loggerName'))

        self.proxyProvider = get(self.options, 'proxyProvider')
        self.proxies = None
        self.proxyListUrl = get(self.options, 'proxyListUrl')

class LocationHelper:
    # a box centered at given coordinates and of a given width
    def getBoundingBoxes(self, inputRow):
        self.initialize()

        result = None

        location = self.getLocationString(inputRow)

        if not location:
            return result

        locations = location.split(';')
        distanceInMiles = get(inputRow, 'distanceInMiles')

        boundingBoxes = []

        for location in locations:
            coordinates = ''

            #zipcode
            if location.isdigit():
                coordinates = self.getCoordinatesForZipCode(location)
            #city
            else:
                coordinates = self.getCoordinatesForCity(location)

            if not coordinates:
                self.log.error(f'Could not find a location for {location}')
                continue

            boundingBox = self.getBoundingBox(coordinates, distanceInMiles)

            boundingBoxes.append(boundingBox)

        if boundingBoxes:
            result = boundingBoxes

        return result

    def getLocationForSearch(self, inputRow):
        self.initialize()
        
        result = ''        
    
        location = self.getLocationString(inputRow)

        if not location:
            return result

        #zipcode
        if location.isdigit():
            coordinates = self.getCoordinatesForZipCode(location)
        #city
        else:
            coordinates = self.getCoordinatesForCity(location)

        if not coordinates:
            return result

        distanceInMiles = get(inputRow, 'distanceInMiles')

        result = f'{coordinates[0]},{coordinates[1]},{distanceInMiles}mi'

        return result

    def getBoundingBox(self, coordinates, distanceInMiles):
        import geopy
        from geopy.distance import VincentyDistance               

        if not coordinates:
            return ''

        origin = geopy.Point(coordinates[0], coordinates[1])

        distanceInKilometers = float(distanceInMiles) * 1.60934
        # southwest corner then northeast corner
        bearings = [225, 45]

        coordinatesList = []

        for bearing in bearings:
            # given: lat1, lon1, b = bearing in degrees, d = distance in kilometers
            destination = VincentyDistance(kilometers=distanceInKilometers).destination(origin, bearing)

            latitude = '{0:.6f}'.format(destination.latitude)
            longitude = '{0:.6f}'.format(destination.longitude)

            string = f'{latitude},{longitude}'

            coordinatesList.append(string)

        result = ','.join(coordinatesList)

        return result

    def getCoordinatesForZipCode(self, zipcodeToFind):
        result = ''
        
        row = self.database.getFirst('zipcode', 'latitude, longitude', f'id = {zipcodeToFind}')

        self.log.debug(f'Row: {row}')
        
        if row:
            result = (get(row, 'latitude'), get(row, 'longitude'))
        
        self.log.debug(f'Coordinates for {zipcodeToFind}: {result}')

        return result

    def getCoordinatesForCity(self, location):
        result = ''
        
        cityToFind = helpers.findBetween(location, '', ',').strip().lower()
        stateToFind = helpers.findBetween(location, ',', '').strip().lower()

        row = self.database.getFirst('city', 'lat, lng', f"city_ascii = '{cityToFind}' and state_id = '{stateToFind}'")

        self.log.debug(f'Row: {row}')
        
        if row:
            result = (get(row, 'lat'), get(row, 'lng'))

        self.log.debug(f'Coordinates for {location}: {result}')

        return result

    def getLocationString(self, inputRow):
        locationFields = [
            'city',
            'state',
            'zipcode'
        ]

        locationParts = []

        for field in locationFields:
            if get(inputRow, field):
                locationParts.append(get(inputRow, field))

        return ', '.join(locationParts)
    
    def initialize(self):
        if self.initialized:
            return True

        self.initialized = True

        self.database = Database('program/resources/zipcodes.sqlite')

    def __init__(self, options):
        self.initialized = False
        self.log = logging.getLogger(get(options, 'loggerName'))


class ThreadHelpers:
    @staticmethod
    def shouldStop(options):
        result = False

        logger = logging.getLogger(get(options, 'loggerName'))
        
        in_q = get(options, 'in_q')
        
        if not in_q or in_q.empty():
            return result

        try:
            message = in_q.get(False)

            if not message:
                return result

            logger.debug(f'Got message from queue: {message}')

            isNewEnough = False
            
            # sent after this run started?
            if get(message, 'gmDate') and get(options, 'gmDateStarted'):
                logger.debug(f'Got message from queue: {message}')

                isNewEnough = get(message, 'gmDate') >= get(options, 'gmDateStarted')
                logger.debug(f'Is new enough: {isNewEnough}')

            if get(message, 'text') == 'shouldStop' and isNewEnough:
                logger.debug(f'Stopping because of message')
                result = True
        except Exception as e:
            helpers.handleException(e)

        return result