"""Replaces google.appengine.api.modules for losers running GAE 1.7.x.

Only use this for tests and the like, it won't do good things in prod.
"""

import os

# Make sure we're not running in prod
assert (os.environ.get("SERVER_SOFTWARE", "Development")
        .startswith('Development')
        and not os.environ.get('FAKE_PROD_APPSERVER'))


def get_current_version_name():
    return 'dev-appserver'


def get_current_module_name():
    return 'default'
