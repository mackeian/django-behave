"""Django test runner which uses behave for BDD tests.
"""

import unittest
from pdb import set_trace
from os.path import dirname, abspath, join, isdir
from os import walk

from django.test.simple import DjangoTestSuiteRunner, reorder_suite
from django.test import LiveServerTestCase, TestCase
from django.db.models import get_app

from behave.configuration import Configuration, ConfigError
from behave.runner import Runner
from behave.parser import ParserError
from behave.formatter.ansi_escapes import escapes

from django_webtest import WebTest
import sys


def get_features(app_module):
    app_dir = dirname(app_module.__file__)
    features_dir = abspath(join(app_dir, 'features'))
    if isdir(features_dir):
        feature_files = []
        for dirpath, dirnames, filenames in walk(features_dir):
            for filename in filenames:
                if filename.endswith('.feature'):
                    feature_files.append(join(dirpath, filename))
        return features_dir, feature_files
    else:
        return None, None

class DjangoBehaveWebTestApp():
    """ Static variable holding the WebTestApp https://bitbucket.org/kmike/django-webtest/
    that can be used inside Django Transactional TestCases"""
    app = None


class DjangoBehaveTestCase(WebTest):
    """ Inheriting from WebTest(TestCase) to get transaction support (and faster tests without setup/teardown of DB between every
     testcase.
     Inherit from LiveServerTestCase if you need other thread accessing (like full stack testing with Selenium)"""

    def __init__(self, **kwargs):
        self.features_dir = kwargs.pop('features_dir')
        super(DjangoBehaveTestCase, self).__init__(**kwargs)
        unittest.TestCase.__init__(self)
        self.setupBehave()

    def get_features_dir(self):
        if isinstance(self.features_dir, basestring):
            return [self.features_dir]
        return self.features_dir

    def setupBehave(self):
        # sys.argv kludge
        # need to understand how to do this better
        # temporarily lose all the options etc
        # else behave will complain
        old_argv = sys.argv
        sys.argv = old_argv[:2]
        self.behave_config = Configuration()
        sys.argv = old_argv
        # end of sys.argv kludge

        #self.behave_config.server_url = self.live_server_url # property of LiveServerTestCase
        #self.behave_config.browser = self.get_browser()
        self.behave_config.paths = self.get_features_dir()
        self.behave_config.format = ['pretty']
        # disable these in case you want to add set_trace in the tests you're developing
        self.behave_config.stdout_capture = False
        self.behave_config.stderr_capture = False

    def runTest(self, result=None):
        # Setting the WebTestApp so it's accessible from e.g. behave steps
        DjangoBehaveWebTestApp.app = self.app

        # run behave on a single directory
        print "run: features_dir=%s" % (self.features_dir)


        # from behave/__main__.py
        stream = self.behave_config.output
        runner = Runner(self.behave_config)
        try:
            failed = runner.run()
        except ParserError, e:
            sys.exit(str(e))
        except ConfigError, e:
            sys.exit(str(e))

        if self.behave_config.show_snippets and runner.undefined:
            msg = u"\nYou can implement step definitions for undefined steps with "
            msg += u"these snippets:\n\n"
            printed = set()

            if sys.version_info[0] == 3:
                string_prefix = "('"
            else:
                string_prefix = u"(u'"

            for step in set(runner.undefined):
                if step in printed:
                    continue
                printed.add(step)

                msg += u"@" + step.step_type + string_prefix + step.name + u"')\n"
                msg += u"def impl(context):\n"
                msg += u"    assert False\n\n"

            sys.stderr.write(escapes['undefined'] + msg + escapes['reset'])
            sys.stderr.flush()

        if failed:
            sys.exit(1)
            # end of from behave/__main__.py

class DjangoBehaveFeatureTestCase(DjangoBehaveTestCase):
    """ Test case that only runs one feature, to avoid database interference between features in same app
    Inherit from django TestCase with transactions gives be smoother and fast, but that does not work with
    external drivers like Selenium etc because of different threads. Only works with djangos own test Client.
    """
    def __init__(self, features_dir, feature_file):
        super(DjangoBehaveFeatureTestCase, self).__init__(features_dir=features_dir)

        # Only include this feature file
        import re
        self.behave_config.include_re = re.compile('%s$' % feature_file)

def make_test_suite(features_dir):
    return DjangoBehaveTestCase(features_dir=features_dir)

def make_feature_test_suite(features_dir, feature_file):
    return DjangoBehaveFeatureTestCase(features_dir, feature_file)

class DjangoBehaveTestSuiteRunner(DjangoTestSuiteRunner):
    def build_suite(self, test_labels, extra_tests=None, **kwargs):
        # build standard Django test suite
        suite = unittest.TestSuite()

        #
        # Add BDD tests to it
        #

        # always get all features for given apps (for convenience)
        for label in test_labels:
            if '.' in label:
                print "Ignoring label with dot in: " % label
                continue
            app = get_app(label)

            # Check to see if a separate 'features' module exists,
            # parallel to the models module
            features_dir, feature_files = get_features(app)
            if features_dir is not None:
                for feature_file in feature_files:
                    # build a test suite for this feature
                    features_test_suite = make_feature_test_suite(features_dir, feature_file)
                    suite.addTest(features_test_suite)
        return reorder_suite(suite, (WebTest,))

# eof:
