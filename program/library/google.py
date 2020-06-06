import logging
import sys
import math

# pip packages
import lxml.html as lh

if '--debug' in sys.argv:
    import helpers as helpers
    from api import Api
    from website import Website
    from other import Internet

    from helpers import get
else:
    from . import helpers
    from .api import Api
    from .website import Website
    from .other import Internet
    
    from .helpers import get

class Google:
    def search(self, query, numberOfResults=10, acceptAll=True, moreParameters={}, start=0):
        results = []

        self.captcha = False
        
        self.api.urlPrefix = self.defaultSearchUrl

        if self.internet:
            self.api.proxies = self.internet.getRandomProxy()

        parameters = {
            'q': query,
            'hl': 'en'
        }

        parameters = helpers.mergeDictionaries(parameters, moreParameters)

        self.resultsPerPage = 10
        pages = numberOfResults / self.resultsPerPage
        startPageIndex = math.ceil(start / self.resultsPerPage)
        endPageIndex = startPageIndex + math.ceil(pages)
        
        for pageIndex in range(startPageIndex, endPageIndex):
            pageResults = self.getSearchPage(query, parameters, numberOfResults, acceptAll, pageIndex)

            if pageResults and numberOfResults == 1:
                return pageResults

            if acceptAll and not self.captcha:
                if not pageResults or pageResults[0] == 'no results' or pageResults == 'no results':
                    break

            results += (pageResults)

        return results

    def getSearchPage(self, query, parameters, numberOfResults, acceptAll, pageIndex):
        if pageIndex > 0:
            parameters['start'] = pageIndex * self.resultsPerPage

        page = self.api.get('/search', parameters, False)

        if '--debug' in sys.argv:
            helpers.toFile(page, 'user-data/logs/page.html')

        results = []

        for i in range(0, self.maximumTries):
            results = self.getSearchResults(page, query, numberOfResults, acceptAll)

            if self.captcha:
                self.log.debug(f'Captcha detected. Try {i + 1} of {self.maximumTries}.')
            else:
                break

        return results

    def getSearchResults(self, page, query, numberOfResults, acceptAll):
        result = ''

        if numberOfResults > 1:
            result = []

        if not self.captcha and 'detected unusual traffic from your computer network.' in page:
            self.log.error(f'There is a captcha')
            self.captcha = True
            return result

        if 'google.' in page and 'did not match any ' in page:
            toDisplay = query.replace('+', ' ')
            self.log.debug(f'No search results for {toDisplay}')

            if numberOfResults == 1:
                return 'no results'
            else:
                return ['no results']

        xpaths = [
            ["//a[contains(@class, ' ') and (contains(@href, '/url?')  or contains(@ping, '/url?'))]", 'href'],
            ["//a[contains(@href, '/url?') or contains(@ping, '/url?')]", 'href'],
            ["//a[contains(@onmousedown, 'return ')]", 'href']
        ]

        document = lh.fromstring(page)

        for xpath in xpaths:
            elements = self.website.getXpathInElement(document, xpath[0], False)

            attribute = xpath[1]

            for element in elements:
                url = element

                if not attribute:
                    url = element.text_content()
                else:
                    url = element.attrib[attribute]

                if self.shouldAvoid(url, acceptAll):
                    continue

                if numberOfResults == 1:
                    result = url
                    break
                else:
                    if not url in result:
                        result.append(url)

                    if len(result) >= numberOfResults:
                        break

            if numberOfResults == 1 and result:
                break
            elif len(result) >= numberOfResults:
                break

        return result

    def shouldAvoid(self, url, acceptAll):
        result = False

        if not url:
            return True

        # avoids internal links
        if not url.startswith('http:') and not url.startswith('https:'):
            return True

        if helpers.substringIsInList(self.avoidPatterns, url):
            return True

        if not acceptAll:
            if helpers.substringIsInList(self.userAvoidPatterns, url):
                return True

            if self.domainMatchesList(url, self.userAvoidDomains):
                return True

            if self.domainMatchesList(url, self.avoidDomains):
                return True

        return result

    def domainMatchesList(self, url, list):
        result = False
        
        domain = helpers.getDomainName(url)

        if domain in list:
            self.log.debug(f'Skipping. Domain is {domain}.')
            return True

        for item in list:
            toFind = f'.{item}'
            
            if domain.endswith(toFind):
                self.log.debug(f'Skipping. Domain ends with {item}.')
                return True

        return result

    def __init__(self, options):
        self.api = Api('', options)
        self.website = Website(options)
        self.captcha = False
        self.avoidDomains = []
        self.userAvoidPatterns = get(options, 'userAvoidPatterns')
        self.userAvoidDomains = get(options, 'userAvoidDomains')
        self.log = logging.getLogger(get(options, 'loggerName'))
        self.internet = Internet(options)
        self.retryOnCaptcha = True
        self.maximumTries = 30

        self.api.setHeadersFromHarFile('program/resources/headers.txt', '')

        self.defaultSearchUrl = 'https://www.google.com'

        if get(options, 'defaultSearchUrl'):
            self.defaultSearchUrl = get(options, 'defaultSearchUrl')

        self.avoidPatterns = [
            'webcache.googleusercontent.com',
            'google.'
        ]
        