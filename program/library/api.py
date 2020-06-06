import sys
import logging
import os.path
import random
import json
import urllib.parse
import requests

from collections import OrderedDict

if '--debug' in sys.argv:
    import helpers as helpers

    from helpers import get
else:
    from . import helpers
    
    from .helpers import get

class Api:
    def get(self, url, parameters=None, responseIsJson=True, returnResponseObject=False):
        return self.request('GET', url, parameters, None, responseIsJson, returnResponseObject)
    
    def post(self, url, data, responseIsJson=True, returnResponseObject=False, parameters=None):
        return self.request('POST', url, parameters, data, responseIsJson, returnResponseObject)

    def request(self, requestType, url, parameters=None, data=None, responseIsJson=True, returnResponseObject=False):
        result = None
        self.error = False
        self.lastStatusCode = None

        self.setHeaders()

        maximumTries = self.maximumTries
        
        reliableDomains = get(self.options, 'reliableDomains').split(' ')

        if reliableDomains and helpers.getDomainName(self.urlPrefix) in reliableDomains:
            maximumTries = self.smallerMaximumTries

        for i in range(0, maximumTries):
            self.error = False

            result = self.tryRequest(requestType, url, parameters, data, responseIsJson, returnResponseObject)

            if self.error:
                self.log.debug(f'Try {i + 1} of {self.maximumTries}')
            else:
                break

        return result

    def tryRequest(self, requestType, url, parameters=None, data=None, responseIsJson=True, returnResponseObject=False):
        result = ''

        if responseIsJson:
            result = {}

        cacheResponse = self.handleDebug(requestType, url, parameters, data, responseIsJson, returnResponseObject)

        if cacheResponse:
            return cacheResponse

        try:
            response = requests.request(requestType, self.urlPrefix + url, params=parameters, headers=self.headers, data=data, proxies=self.proxies, timeout=self.timeout, verify=self.verify)

            self.handleResponseLog(requestType, url, parameters, data, response)
            
            if returnResponseObject:
                result = response
            elif responseIsJson:
                result = json.loads(response.text)
            else:
                result = response.text
        
        except Exception as e:
            self.error = True
            
            if 'Max retries exceeded with url' in str(e):
                helpers.handleException(e, None, self.log.name, True)
            else:
                helpers.handleException(e, None, self.log.name)
        
        return result

    def getPlain(self, url):
        result = self.get(url, None, False)

        return result

    def getFinalUrl(self, url):
        if not url:
            return url

        response = self.get(url, None, False, returnResponseObject=True)

        if not response or not hasattr(response, 'url'):
            return url
        
        result = response.url

        # because the protocol can change in the above steps
        if helpers.findBetween(result, '://', '') == helpers.findBetween(url, '://', ''):
            # for javascript redirects
            redirect = helpers.findBetween(response.text, 'location.replace("', '")', strict=True)
            
            if redirect:
                result = redirect.replace(r'\/', '/')

        return result

    def downloadBinaryFile(self, url, destinationFileName):       
        result = False
        
        import wget
        
        self.log.debug(f'Download {url} to {destinationFileName}')
        
        try:
            wget.download(url, destinationFileName)
            result = True
        except Exception as e:
            self.log.error(e)
        
        return result

    def handleDebug(self, requestType, url, parameters, data, responseIsJson, returnResponseObject):
        self.cacheFileName = ''

        parameterString = ''

        if parameters:
            parameterString += '?' + urllib.parse.urlencode(parameters)

        self.log.debug(f'{requestType} {self.urlPrefix}{url}{parameterString}')
        self.log.debug(f'Request parameters: {parameters}')
        self.log.debug(f'Request headers: {self.headers}')
        self.log.debug(f'Request body: {data}')

        if not '--debug' in sys.argv:
            return None
        else:
            self.verify = False

        if requestType == 'POST' and not self.cachePostRequests:
            return None
       
        self.cacheFileName = self.getCacheFileName(url, parameters, data, responseIsJson)

        return self.getCacheResponse(responseIsJson, returnResponseObject)

    def getCacheResponse(self, responseIsJson, returnResponseObject):
        if '--noCache' in sys.argv or not os.path.exists(self.cacheFileName):
            return None

        self.log.debug('Using cached version')

        result = helpers.getFile(self.cacheFileName)
        
        if returnResponseObject:
            content = helpers.getBinaryFile(self.cacheFileName)

            from types import SimpleNamespace
            d = {
                'content': content,
                'text': result,
                'status_code': 200
            }
            
            n = SimpleNamespace(**d)
            
            return n
        elif responseIsJson:
            return json.loads(result)
        else:
            return result

    def handleResponseLog(self, requestType, url, parameters, data, response):
        # got a response. it might be an error status code.
        self.error = False
        self.lastStatusCode = response.status_code

        self.log.debug(f'Response code: {response.status_code}')
        self.log.debug(f'Response headers: {response.headers}')

        if response.text != None:
            self.log.debug(f'Response: {response.text[0:500]}...')

        # response empty or is 4xx or 5xx?        
        if not response:
            self.log.debug(f'Something went wrong with the response. Status code: {response.status_code}.')
            return
               
        if '--debug' in sys.argv and ('maps.google' in self.urlPrefix and 'INVALID_REQUEST' in response.text):
            return

        helpers.makeDirectory('user-data/logs/cache')

        if '--debug' in sys.argv and self.cacheFileName:
            helpers.toBinaryFile(response.content, self.cacheFileName)

            parameterString = ''

            if parameters:
                parameterString += '?' + urllib.parse.urlencode(parameters)

            urlForFile = f'{self.urlPrefix}{url}{parameterString}'

            if data:
                urlForFile += f'?hashOfData={helpers.hash(data)}'

            # avoid duplicates when using returnResponseObject
            if not f' {urlForFile}' in helpers.getFile('user-data/logs/cache.txt'):               
                helpers.appendToFile(f'{self.cacheFileName} {urlForFile}', 'user-data/logs/cache.txt')
        # normal log
        else:
            number = '{:02d}'.format(self.requestIndex)
            
            fileName = f'user-data/logs/cache/{helpers.lettersAndNumbersOnly(self.urlPrefix)}-{number}.json'
            
            self.requestIndex += 1

            if self.requestIndex >= 100:
                self.requestIndex = 0

            self.log.debug(f'Writing response to {fileName}')
            helpers.toBinaryFile(response.content, fileName)

    def getCacheFileName(self, url, parameters, data, responseIsJson):
        result = ''

        file = helpers.getFile('user-data/logs/cache.txt')

        urlToFind = self.urlPrefix + url
       
        if parameters:
            urlToFind += '?' + urllib.parse.urlencode(parameters)

        if data:
            urlToFind += f'?hashOfData={helpers.hash(data)}'

        for line in file.splitlines():
            fileName = helpers.findBetween(line, '', ' ')
            lineUrl = helpers.findBetween(line, ' ', '')

            if lineUrl == urlToFind:
                result = fileName
                break

        if not result:
            fileName = helpers.lettersAndNumbersOnly(url)
            fileName = fileName[0:25]
            
            for i in range(0, 16):  
                fileName += str(random.randrange(0, 10))
            
            extension = 'json'

            if not responseIsJson:
                extension = 'html'

            result = f'user-data/logs/cache/{fileName}.{extension}'

        return result

    def getHeadersFromTextFile(self, fileName):
        result = OrderedDict()

        lines = helpers.getFile(fileName).splitlines()

        list = []
        cookies = []

        foundCookie = False

        for line in lines:
            name = helpers.findBetween(line, '', ': ')
            value = helpers.findBetween(line, ': ', '')

            if name.lower() == 'cookie':
                if not foundCookie:
                    foundCookie = True                    
                else:
                    cookies.append(value)
                    continue
            
            item = (name, value)

            list.append(item)

        if list:
            result = OrderedDict(list)

            if foundCookie and cookies:
                result['cookie'] += '; ' + '; '.join(cookies)

        return result

    def setHeaders(self):
        if not self.usedHarFile and get(self.options, 'randomizeUserAgent'):
            for key in self.headers.keys():
                if key.lower() == 'user-agent':
                    self.headers[key] = random.choice(self.userAgentList)
                    break

    def setHeadersFromHarFile(self, fileName, urlMustContain, replacements={}):
        if not os.path.exists(fileName):
            return

        self.usedHarFile = True

        try:
            from pathlib import Path
            
            headersList = []
            
            if Path(fileName).suffix == '.har':
                from haralyzer import HarParser
            
                file = helpers.getFile(fileName)

                j = json.loads(file)

                har_page = HarParser(har_data=j)

                # find the right url
                for page in har_page.pages:
                    for entry in page.entries:
                        if urlMustContain in entry['request']['url']:
                            headersList = entry['request']['headers']
                            break

            else:
                headersList = helpers.getJsonFile(fileName)
                headersList = get(headersList, 'headers')

            headers = []

            for name, value in replacements.items():
                newHeader = (name, value)
                headers.append(newHeader)

            for header in headersList:
                name = header.get('name', '')
                value = header.get('value', '')

                # ignore pseudo-headers
                if name.startswith(':'):
                    continue
                elif name.lower() == 'content-length' or name.lower() == 'host':
                    continue                
                # don't overwrite these headers
                elif get(replacements, name):
                    continue
                # otherwise response will stay compressed and unreadable
                elif name.lower() == 'accept-encoding' and not self.hasBrotli:
                    value = value.replace(', br', '')
                elif name.lower() == 'user-agent' and get(self.options, 'randomizeUserAgent'):
                    value = random.choice(self.userAgentList)

                newHeader = (name, value)

                headers.append(newHeader)

            self.headers = OrderedDict(headers)
        
        except Exception as e:
            helpers.handleException(e)

    def getHeadersFromFile(self, fileName):
        file = helpers.getFile(fileName)

        if not file:
            return

        j = json.loads(file)

        newHeaders = []

        for header in j.get('headers', ''):
            name = header.get('name', '')

            # ignore pseudo-headers
            if name.startswith(':'):
                continue

            if name.lower() == 'content-length' or name.lower() == 'host':
                continue

            newHeader = (name, header.get('value', ''))

            newHeaders.append(newHeader)

        return OrderedDict(newHeaders)

    def randomizeHeaders(self):
        self.headers = self.getHeadersFromFile(f'program/resources/headers.txt')

    def lastStatusCodeIsError(self):
        result = False

        if self.lastStatusCode == None:
            return result
        
        string = str(self.lastStatusCode)

        if string.startswith('4') or string.startswith('5'):
            result = True

        return result

    def __init__(self, urlPrefix='', options=None):
        self.options = options
        self.urlPrefix = urlPrefix
        self.timeout = 10
        self.requestIndex = 0
        self.log = logging.getLogger(get(options, 'loggerName'))
        self.cacheFileName = ''
        self.smallerMaximumTries = 2
        self.maximumTries = 3
        self.error = False
        self.usedHarFile = False
        self.lastStatusCode = None

        self.randomizeHeaders()

        self.userAgentList = None
        
        if get(self.options, 'randomizeUserAgent'):
            file = helpers.getFile('program/resources/user-agents.txt')
            self.userAgentList = file.splitlines()

        if not self.headers:
            if not self.userAgentList:
                self.userAgentList = [
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36'
                ]

            userAgent = random.choice(self.userAgentList)

            self.headers = OrderedDict([
                ('user-agent', userAgent),
                ('accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9'),
                ('accept-language', 'en-US,en;q=0.9')
            ])

        self.proxies = None
        self.verify = True
        self.hasBrotli = True
        self.cachePostRequests = False

        try:
            import brotli
        except ImportError as e:
            self.hasBrotli = False
            helpers.handleException(e, 'You should run "pip3 install brotli" or "pip install brotli" first, then restart this script')