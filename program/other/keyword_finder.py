import os
import sys
import logging
import json
import time
import re

from datetime import datetime, date, timedelta, timezone

if '--debug' in sys.argv:
    import helpers as helpers

    from database import Database
    from api import Api
    from google import Google

    from helpers import get
else:
    import program.library.helpers as helpers

    from ..library.database import Database
    from ..library.api import Api
    from ..library.google import Google

    from program.library.helpers import get

class KeywordFinder:
    def runRepeatedly(self):
        while True:
            try:
                self.run()
                self.waitForNextRun()
            except Exception as e:
                helpers.handleException(e)

    def run(self):
        self.log.info('Starting search')
        
        self.gmDateStarted = datetime.utcnow()
        self.newResults = []
        self.optionsFromDatabase = self.getOptionsFromDatabase()
        self.inputRows = self.getInputRows()
        self.removeOldEntries()

        newRow = {
            'name': 'lastRunDate',
            'value': self.gmDateStarted.strftime('%Y-%m-%d %H:%M:%S')
        }

        self.database.insert('option', newRow)

        for i, inputRow in enumerate(self.inputRows):
            try:
                self.logHistory(f'On item {i + 1} of {len(self.inputRows)}: {get(inputRow, "Ds Company Website")}.')
                self.search(inputRow)
            except Exception as e:
                helpers.handleException(e)

    def search(self, inputRow):
        url = get(inputRow, 'Ds Company Website')

        if self.alreadyDone(url):
            return

        if not url.startswith('http'):
            url = 'http://' + url

        domainToUse = helpers.getDomainName(url)

        queryList = []

        for keyword in self.keywords:
            queryList.append(f'"{keyword}"')

        query = ' OR '.join(queryList)

        urls = self.google.search(f'site:{domainToUse} {query}')

        if self.google.captcha:
            self.log.error(f'Skipping this line. There is a captcha.')
            return

        self.log.info(f'Results from google: {urls}')

        # use main page as a backup
        if not urls:
            urls.append(url)

        matchingKeywords = []
        
        for searchResultUrl in urls:
            if helpers.getBasicDomainName(searchResultUrl) != helpers.getBasicDomainName(url):
                continue

            matchingKeywords += self.getMatchingKeywords(searchResultUrl)

        matchingKeywords = ';'.join(matchingKeywords)

        newResult = {
            'url': url,
            'keyword': matchingKeywords
        }

        self.newResults.append(newResult)
        self.store(inputRow, url, matchingKeywords)

        if not matchingKeywords:
            self.logHistory(f'No results for {url}')

    def getMatchingKeywords(self, searchResultUrl):
        # default to none, in case can't find which keyword matches
        # google may have search results that don't actually contain any of the keywords
        results = []

        api = Api('', self.options)
        
        self.log.info(f'Checking {searchResultUrl}')

        page = api.getPlain(searchResultUrl)
        lowercasePage = page.lower()

        for keyword in self.keywords:
            if keyword.lower() in lowercasePage:
                self.log.info(f'New result: {keyword}')
                results.append(keyword)                

        for keyword in self.keywordsCaseSensitive:
            if keyword in page:
                self.log.info(f'New result: {keyword}')
                results.append(keyword)

        if not results:
            self.log.info(f'No keywords are on {searchResultUrl}')

        return results

    def logHistory(self, text):
        self.log.info(text)

        newRow = {
            'gmDate': str(datetime.utcnow()),
            'text': text
        }

        self.database.insert('history', newRow)

    def alreadyDone(self, url):
        result = False

        row = self.database.getFirst('result', '*', f"url = '{self.database.escape(url)}'")

        if row:
            self.log.info(f'Skipping {url}. Already done.')
            result = True

        return result

    def store(self, inputRow, url, matchingKeywords):
        newRow = {
            'url': get(inputRow, 'Ds Company Website'),
            'matchingUrl': url,
            'keyword': matchingKeywords,
            'gmDate': str(datetime.utcnow()),
        }

        self.database.insert('result', newRow)

        outputFile = self.options['outputFile']
        
        fields = ['Ds Id', 'Ds Company Website']

        for keyword in self.keywords:
            fields.append(keyword)

        if not os.path.exists(outputFile):        
            helpers.toFile(','.join(fields) + '\n', outputFile)

        values = [
            get(inputRow, 'Ds Id'),
            get(inputRow, 'Ds Company Website'),
        ]

        matchingKeywordsList = matchingKeywords.split(';')

        for keyword in self.keywords:
            if keyword in matchingKeywordsList:
                values.append(keyword)
            else:
                values.append('')

        # this quotes fields that contain commas
        helpers.appendCsvFile(values, outputFile)

    def getOptionsFromDatabase(self):
        result = {}

        rows = self.database.get('option')

        for row in rows:
            name = get(row, 'name')
            value = get(row, 'value')

            result[name] = value

        return result

    def getInputRows(self):
        results = []

        urls = get(self.optionsFromDatabase, 'urls')

        for url in urls.splitlines():
            inputRow = {
                'url': helpers.findBetween(url, '', ' '),
                'keywords': helpers.findBetween(url, ' ', '', True)
            }

            results.append(inputRow)

        if not results:
            results = helpers.getCsvFile(self.options['inputFile'])

        return results

    def waitForNextRun(self):
        hours = get(self.optionsFromDatabase, 'hoursBetweenRuns')

        if hours:
            hours = int(hours)

        if not hours:
            hours = int(self.options['hoursBetweenRuns'])

        self.log.info(f'Done for today. Will run again in {hours} hours.')

        nextDay = self.gmDateStarted + timedelta(hours=hours)

        newRow = {
            'name': 'nextRunDate',
            'value': nextDay.strftime('%Y-%m-%d %H:%M:%S')
        }

        self.database.insert('option', newRow)

        self.waitUntil(nextDay)

    def waitUntil(self, dateObject):
        self.log.info(f'Waiting until {dateObject}')

        while True:
            if datetime.utcnow() >= dateObject:
                break

            row = self.database.getFirst('option', '*', f"name = 'checkNow'")

            if get(row, 'value') == '1':
                self.log.info('User pressed check now')

                # turn it off
                newRow = {
                    'name': 'checkNow',
                    'value': '0'
                }

                self.database.insert('option', newRow)

                break

            time.sleep(3)

        self.log.info('Done waiting')

    def removeOldEntries(self):
        maximumDaysToKeepItems = self.options['maximumDaysToKeepItems']

        minimumDate = helpers.getDateStringSecondsAgo(maximumDaysToKeepItems * 24 * 60 * 60, True)
        
        self.log.debug(f'Deleting entries older than {maximumDaysToKeepItems} days')
        
        self.database.execute(f"delete from result where gmDate < '{minimumDate}'")
        self.database.execute(f"delete from history where gmDate < '{minimumDate}'")

    def __init__(self, options, credentials):
        self.options = options
        self.log = logging.getLogger(get(self.options, 'loggerName'))
        self.newResults = []
        
        self.keywords = helpers.getFile('user-data/input/keywords.txt')
        self.keywords = self.keywords.splitlines()

        self.keywordsCaseSensitive = helpers.getFile('user-data/input/keywords-case-sensitive.txt')
        self.keywordsCaseSensitive = self.keywordsCaseSensitive.splitlines()

        self.database = Database('user-data/database.sqlite')
        self.database.makeTables('program/resources/tables.json')
        
        self.google = Google(self.options)