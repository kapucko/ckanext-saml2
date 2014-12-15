import logging
import uuid

from saml2 import BINDING_HTTP_REDIRECT

import ckan.plugins as p
import ckan.lib.base as base
import ckan.logic as logic
import ckan.lib.helpers as h
import ckan.model as model
import ckan.logic.schema as schema

log = logging.getLogger('ckanext.saml2')


def _no_permissions(context, msg):
    user = context['user']
    return {'success': False, 'msg': msg.format(user=user)}


@logic.auth_sysadmins_check
def user_create(context, data_dict):
    msg = p.toolkit._('Users cannot be created.')
    return _no_permissions(context, msg)


@logic.auth_sysadmins_check
def user_update(context, data_dict):
    msg = p.toolkit._('Users cannot be edited.')
    return _no_permissions(context, msg)


@logic.auth_sysadmins_check
def user_reset(context, data_dict):
    msg = p.toolkit._('Users cannot reset passwords.')
    return _no_permissions(context, msg)


@logic.auth_sysadmins_check
def request_reset(context, data_dict):
    msg = p.toolkit._('Users cannot reset passwords.')
    return _no_permissions(context, msg)

rememberer_name = None

def delete_cookies():
    global rememberer_name
    if rememberer_name is None:
        plugins = p.toolkit.request.environ['repoze.who.plugins']
        saml_plugin = plugins.get('saml2auth')
        rememberer_name = saml_plugin.rememberer_name
    base.response.delete_cookie(rememberer_name)
    # We seem to end up with an extra cookie so kill this too
    domain = p.toolkit.request.environ['HTTP_HOST']
    base.response.delete_cookie(rememberer_name, domain='.' + domain)

class Saml2Plugin(p.SingletonPlugin):

    p.implements(p.IAuthenticator, inherit=True)
    p.implements(p.IRoutes, inherit=True)
    p.implements(p.IAuthFunctions, inherit=True)
    p.implements(p.IConfigurable)


    saml_identify = None

    def make_mapping(self, key, config):
        data = config.get(key)
        mapping = {}
        for item in data.split():
            bits = item.split('~')
            mapping[bits[0]] = bits[1]
        return mapping

    def configure(self, config):
        self.user_mapping = self.make_mapping('saml2.user_mapping', config)
        m = self.make_mapping('saml2.organization_mapping', config)
        self.organization_mapping = m

    def before_map(self, map):
        map.connect(
            'saml2_unauthorized',
            '/saml2_unauthorized',
            controller='ckanext.saml2.plugin:Saml2Controller',
            action='saml2_unauthorized'
        )
        map.connect(
            'saml2_slo',
            '/slo',
            controller='ckanext.saml2.plugin:Saml2Controller',
            action='slo'
        )
        return map

    def make_password(self):
        # create a hard to guess password
        out = ''
        for n in xrange(8):
            out += str(uuid.uuid4())
        return out

    def identify(self):
        ''' This does work around saml2 authorization.
        c.user contains the saml2 id of the logged in user we need to
        convert this to represent the ckan user. '''

        # Can we find the user?
        c = p.toolkit.c
        environ = p.toolkit.request.environ
        log.info('---environ---')
        log.info(environ)
        user = environ.get('REMOTE_USER', '')
        log.info('user')
        log.info(user)
        #log.info("repoze.who.identity: '%s'" % environ.get("repoze.who.identity", ""))
        i = environ.get("repoze.who.identity", "")
        if i:
        #    log.info(dir(i))
            log.info(i.viewkeys())
        #    log.info(i['repoze.who.userid'])
            log.info(i['user'])
            log.info(i.get('userdata', 'no user data'))
        if not user:
            user = environ.get("repoze.who.identity", "")
            log.info("repoze.who.identity: '%s'" % user)
        if user:
            # we need to get the actual user info from the saml2auth client
            if not self.saml_identify:
                plugins = environ['repoze.who.plugins']
                saml_plugin = plugins.get('saml2auth')
                if not saml_plugin:
                    # saml2 repoze plugin not set up
                    return
                saml_client = saml_plugin.saml_client
                self.saml_identify = saml_client.users.get_identity

            identity = environ.get("repoze.who.identity", {})
            user_data = identity.get("user", {})
            # If we are here but no info then we need to clean up
            if not user_data:
                delete_cookies()
                h.redirect_to(controller='user', action='logged_out')
            
            log.info('---getting name---')
            c.user = user_data['actor_username'][0]
            c.userobj = model.User.get(c.user)

            if c.userobj is None:
                # Create the user
                data_dict = {
                    'password': self.make_password(),
                    'name' : user_data['actor_username'][0],
                    'email' : user_data['actor_email'][0],
                    'fullname' : user_data['actor_formatted_name'][0],
                    'id' : user_data['actor_upvs_identity_id'][0]
                }
                #self.update_data_dict(data_dict, self.user_mapping, saml_info)
                # Update the user schema to allow user creation
                user_schema = schema.default_user_schema()
                log.info('---schema---')
                log.info(user_schema)
                user_schema['id'] = [p.toolkit.get_validator('not_empty')]
                user_schema['name'] = [p.toolkit.get_validator('not_empty')]
                user_schema['email'] = [p.toolkit.get_validator('ignore_missing')]

                context = {'schema' : user_schema, 'ignore_auth': True}
                user = p.toolkit.get_action('user_create')(context, data_dict)
                c.userobj = model.User.get(c.user)

            # check if this is the first time we are authorized
            # If so check the users org is done
            #if 'user' in environ.get('repoze.who.identity',{}):
            #    if self.organization_mapping['name'] in saml_info:
            #        self.create_organization(saml_info)

    def create_organization(self, saml_info):
        org_name = saml_info[self.organization_mapping['name']][0]
        org = model.Group.get(org_name)

        context = {'ignore_auth': True}
        site_user = p.toolkit.get_action('get_site_user')(context, {})
        c = p.toolkit.c

        if not org:
            context = {'user': site_user['name']}
            data_dict = {
            }
            self.update_data_dict(data_dict, self.organization_mapping, saml_info)
            org = p.toolkit.get_action('organization_create')(context, data_dict)
            org = model.Group.get(org_name)

        # check if we are a member of the organization
        data_dict = {
            'id': org.id,
            'type': 'user',
        }
        members = p.toolkit.get_action('member_list')(context, data_dict)
        members = [member[0] for member in members]
        if c.userobj.id not in members:
            # add membership
            member_dict = {
                'id': org.id,
                'object': c.userobj.id,
                'object_type': 'user',
                'capacity': 'member',
            }
            member_create_context = {
                'user': site_user['name'],
                'ignore_auth': True,
            }

            p.toolkit.get_action('member_create')(member_create_context, member_dict)


    def update_data_dict(self, data_dict, mapping, saml_info):
        for field in mapping:
            value = saml_info.get(mapping[field])
            if value:
                # If list get first value
                if isinstance(value, list):
                    value = value[0]
                if not field.startswith('extras:'):
                    data_dict[field] = value
                else:
                    if 'extras' not in data_dict:
                        data_dict['extras'] = []
                    data_dict['extras'].append(dict(key=field[7:], value=value))

    def login(self):
        # We can be here either because we are requesting a login (no user)
        # or we have just been logged in.
        if not p.toolkit.c.user:
            # A 401 HTTP Status will cause the login to be triggered
            return base.abort(401, p.toolkit._('Login required!'))
        h.redirect_to(controller='user', action='dashboard')


    def logout(self):
        environ = p.toolkit.request.environ
        subject_id = environ["repoze.who.identity"]['repoze.who.userid']
        client = environ['repoze.who.plugins']["saml2auth"]
        saml_logout = client.saml_client.global_logout(subject_id, sign=True)
        log.info('rememberer_name')
        log.info(client.rememberer_name)
        rem = environ['repoze.who.plugins'][client.rememberer_name]
        rem.forget(environ, subject_id)
        # do the redirect the url is in the saml_logout
        log.info('---saml_logout---')
        log.info(saml_logout)
        help = saml_logout[saml_logout.keys()[0]][1]
        url = help['headers'][0][1].replace(' ', '')
        log.info(url)
        h.redirect_to(url)

    def abort(self, status_code, detail, headers, comment):
        # HTTP Status 401 causes a login redirect.  We need to prevent this
        # unless we are actually trying to login.
        if (status_code == 401
            and p.toolkit.request.environ['PATH_INFO'] != '/user/login'):
                h.redirect_to('saml2_unauthorized')
        return (status_code, detail, headers, comment)

    def get_auth_functions(self):
        # we need to prevent some actions being authorized.
        return {
            'user_create': user_create,
            'user_update': user_update,
            'user_reset': user_reset,
            'request_reset': request_reset,
        }


class Saml2Controller(base.BaseController):

    def saml2_unauthorized(self):
        # This is our you are not authorized page
        c = p.toolkit.c
        c.code = 401
        c.content = p.toolkit._('You are not authorized to do this')
        return p.toolkit.render('error_document_template.html')

    def slo(self):
        environ = p.toolkit.request.environ
        # so here I might get either a LogoutResponse or a LogoutRequest
        client = environ['repoze.who.plugins']['saml2auth']
        if 'QUERY_STRING' in environ:
            saml_resp = p.toolkit.request.GET.get('SAMLResponse', '')
            saml_req = p.toolkit.request.GET.get('SAMLRequest', '')

            if saml_req:
                log.info('SAML REQUEST for logout recieved')
                get = p.toolkit.request.GET
                subject_id = environ["repoze.who.identity"]['repoze.who.userid']
                headers, success = client.saml_client.do_http_redirect_logout(get, subject_id)
                h.redirect_to(headers[0][1])
            elif saml_resp:
             ##   # fix the cert so that it is on multiple lines
             ##   out = []
             ##   # if on multiple lines make it a single one
             ##   line = ''.join(saml_resp.split('\n'))
             ##   while len(line) > 64:
             ##       out.append(line[:64])
             ##       line = line[64:]
             ##   out.append(line)
             ##   saml_resp = '\n'.join(out)
             ##   try:
             ##       res = client.saml_client.logout_request_response(
             ##           saml_resp,
             ##           binding=BINDING_HTTP_REDIRECT
             ##       )
             ##   except KeyError:
             ##       # return error reply
             ##       pass

                delete_cookies()
                h.redirect_to(controller='user', action='logged_out')
