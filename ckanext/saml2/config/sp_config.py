import os.path

from saml2 import BINDING_HTTP_REDIRECT
from saml2.saml import NAME_FORMAT_BASIC

try:
    from saml2.sigver import get_xmlsec_binary
except ImportError:
    get_xmlsec_binary = None

if get_xmlsec_binary:
    xmlsec_path = get_xmlsec_binary(["/opt/local/bin"])
else:
    xmlsec_path = '/usr/bin/xmlsec1'


#BASE = 'http://edem.microcomp.sk'
#entityid' : 'http://edem.microcomp.sk',
BASE = 'http://edem.microcomp.sk'
CONFIG_PATH = os.path.dirname(__file__)

USER_MAPPING = {
    'email': 'mail',
    'fullname': 'field_display_name',
}
#'idp': ['urn:mace:umu.se:saml:ckan:idp'],
CONFIG = {
    'entityid' : 'http://edem.microcomp.sk',
    'description': 'CKAN saml2 auth',
    'service': {
        'sp': {
            'name' : 'CKAN SP',
            'endpoints': {
                'assertion_consumer_service': [BASE],
                'single_logout_service' : [(BASE + '/slo',
                                            BINDING_HTTP_REDIRECT)],
            },
            'required_attributes': [
              #  'sn',
                'uid',
              #  'name',
              #  'mail',
              #  'status',
              #  'roles',
              #  'field_display_name',
              #  'realname',
              #  'groups',
              #  'givenname',
              #  'surname',
              #  'edupersonaffiliation',
            ],
            'optional_attributes': [],
            "authn_assertions_signed": "true",
            "authn_requests_signed" : "true",
            "want_assertions_signed": "true",
            "logout_requests_signed": "true",
        }
    },
    'debug': 1,
    'key_file': CONFIG_PATH + '/pki/mod_key.pem',
    'cert_file': CONFIG_PATH + '/pki/mod_cert.pem',
    'attribute_map_dir': CONFIG_PATH + '/../attributemaps',
    'metadata': {
       'local': [CONFIG_PATH + '/idp.xml'],
    },
    # -- below used by make_metadata --
#    'organization': {
#        'name': 'Exempel AB',
#        'display_name': [('Exempel AB','se'),('Example Co.','en')],
#        'url':'http://www.example.com/ckan',
#    },
#    'contact_person': [{
#        'given_name':'John',
#        'sur_name': 'Smith',
#        'email_address': ['john.smith@example.com'],
#        'contact_type': 'technical',
#        },
#    ],
    'name_form': NAME_FORMAT_BASIC,
    "xmlsec_binary": '/usr/bin/xmlsec1',
    'logger': {
        'rotating': {
            'filename': 'sp.log',
            'maxBytes': 100000,
            'backupCount': 5,
            },
        'loglevel': 'debug',
    }
}
