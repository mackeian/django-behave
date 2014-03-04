"""Django test runner which uses behave for BDD tests.
"""

import unittest
import glob
from os.path import dirname, abspath, join

from django.conf import settings
from django.db.models import get_app
from django.test.simple import DjangoTestSuiteRunner, reorder_suite
from django.test import LiveServerTestCase


import behave
from behave.configuration import Configuration, ConfigError
from behave.runner import Runner
from behave.parser import ParserError
from behave.formatter.ansi_escapes import escapes

import sys

def get_feature_paths(app_module, feature_name):
    app_dir = dirname(app_module.__file__)
    path_to_features = abspath(join(app_dir, 'tests/features'))
    if feature_name:
        # Return only that specific feature
        feature_paths = [join(path_to_features, feature_name + '.feature')]
    else:
        # Return all feature files (so each file can be run in an own transactionTestCase)
        feature_paths = glob.glob(path_to_features + '/*.feature')

    return feature_paths


class DjangoTestCaseAccessor():
    test_case = None


class DjangoBehaveTestCase(LiveServerTestCase):
    def __init__(self, features_dir=None, feature_paths=None):
        super(DjangoBehaveTestCase, self).__init__()
        if features_dir:
            self.feature_paths = [features_dir]
        else:
            self.feature_paths = feature_paths
        # sys.argv kludge
        # need to understand how to do this better
        # temporarily lose all the options etc
        # else behave will complain
        old_argv = sys.argv
        sys.argv = old_argv[:2]

        # Append settings
        if getattr(settings, 'DJANGO_BEHAVE_JUNIT', False):
            sys.argv.append('--junit')

        self.behave_config = Configuration()
        sys.argv = old_argv
        # end of sys.argv kludge
        self.behave_config.paths = self.feature_paths
        self.behave_config.format = ['pretty']

        self.behave_config.server_url =  'http://localhost:8081'

        # disable these in case you want to add set_trace in the tests you're developing
        #self.behave_config.stdout_capture = False
        #self.behave_config.stderr_capture = False

        DjangoTestCaseAccessor.test_case = self

    def runTest(self, result=None):
        # run behave on a single directory
        print "Run test in transaction for feature_paths=%s" % self.feature_paths

        # from behave/__main__.py
        runner = Runner(self.behave_config)
        try:
            failed = runner.run()
        except ParserError, e:
            sys.exit(str(e))
        except ConfigError, e:
            sys.exit(str(e))

        if self.behave_config.show_snippets and hasattr(runner, 'undefined') and runner.undefined:
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

        self.assertFalse(failed)


def make_test_suite(features_dir):
    return DjangoBehaveTestCase(features_dir=features_dir)

def make_test_suite_from_paths(feature_paths):
    return DjangoBehaveTestCase(feature_paths=feature_paths)


class DjangoBehave_Runner(DjangoTestSuiteRunner):
    def build_suite(self, test_labels, extra_tests=None, **kwargs):
        suite = unittest.TestSuite()
        # always get all features for given apps (for convenience)
        for label in test_labels:
            print label
            if '.' in label:
                parts = label.split('.')
                label = parts[0]
                feature_name = parts[1]
            else:
                feature_name = None
            app = get_app(label)
            
            # Check to see if a separate 'features' module exists,
            # parallel to the models module
            feature_paths = get_feature_paths(app, feature_name)
            for feature_path in feature_paths:
                # build a test suite for each feature path, to let them run in separate transactions
                features_test_suite = make_test_suite(feature_path)
                suite.addTest(features_test_suite)

        return reorder_suite(suite, (LiveServerTestCase,))

# eof:
