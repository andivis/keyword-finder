import sys

if '--debug' in sys.argv:
    import helpers as helpers

    from helpers import get
else:
    import program.library.helpers as helpers

    from program.library.helpers import get

from program.other.keyword_finder import KeywordFinder

class Main:
    def run(self):
        self.log.info('Starting')

        try:
            keywordFinder = KeywordFinder(self.options, self.credentials)
            keywordFinder.run()
        except Exception as e:
            helpers.handleException(e)
        
        self.log.info('Done')

    def __init__(self):
        self.loggerHandlers = helpers.setUpLogging('user-data/logs')
        self.log = self.loggerHandlers['logger']

        # set default options
        self.options = {
            'inputFile': 'user-data/input/input.csv',
            'outputFile': 'user-data/output/output.csv',
            'daysBetweenDuplicates': -1,
            'loggerName': self.log.name,
            'maximumDaysToKeepItems': 90,
            'randomizeUserAgent': 1
        }

        # read the options file
        optionsFileName = helpers.getParameter('--optionsFile', False, 'user-data/options.ini')        
        helpers.setOptions(optionsFileName, self.options)

        variables = {
            'product-name': get(self.options, 'productName'),
            'product-name-id': helpers.getId(get(self.options, 'productName')),
            'server-domain': helpers.getDomainName(get(self.options, 'serverUrl'))
        }

        self.options['fromEmailAddress'] = helpers.replaceVariables(get(self.options, 'fromEmailAddress'), variables, '$')
        self.options['debugEmailAddress'] = helpers.replaceVariables(get(self.options, 'debugEmailAddress'), variables, '$')

        self.credentials = {}
        helpers.setOptions('user-data/credentials/credentials.ini', self.credentials, '')

if __name__ == '__main__':
    main = Main()
    main.run()