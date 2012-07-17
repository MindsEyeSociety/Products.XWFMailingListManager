# Copyright IOPEN Technologies Ltd., 2003
# richard@iopen.net
#
# For details of the license, please see LICENSE.
#
# You MUST follow the rules in README_STYLE before checking in code
# to the head. Code which does not follow the rules will be rejected.  
#
from zope.component import createObject
from AccessControl import ClassSecurityInfo

from Products.PageTemplates.PageTemplateFile import PageTemplateFile
from App.class_init import InitializeClass
from OFS.Folder import Folder

from Products.XWFCore.XWFUtils import get_support_email
from Products.XWFCore.XWFUtils import get_group_by_siteId_and_groupId
from gs.cache import cache

# TODO: once catalog is completely removed, we can remove XWFMetadataProvider too
from Products.XWFCore.XWFMetadataProvider import XWFMetadataProvider

from Products.XWFMailingListManager.queries import MessageQuery, DigestQuery 
from Products.XWFMailingListManager.queries import BounceQuery
from bounceaudit import BounceHandlingAuditor, BOUNCE, DISABLE

import os, time, logging, StringIO, traceback
from Products.CustomUserFolder.queries import UserQuery
from Products.CustomUserFolder.userinfo import IGSUserInfo
from Products.GSGroup.groupInfo import IGSGroupInfo
from gs.profile.email.base.emailuser import EmailUser
from gs.profile.notify.notifyuser import NotifyUser
import sqlalchemy as sa
import datetime

log = logging.getLogger('XWFMailingListManager.XWFMailingListManager')

class Record:
    pass

class XWFMailingListManager(Folder, XWFMetadataProvider):
    """ A searchable, self indexing mailing list manager.

    """
    security = ClassSecurityInfo()
    security.setPermissionDefault('View', ('Manager',))

    meta_type = 'XWF Mailing List Manager'
    version = 0.99
    
    manage_options = Folder.manage_options + \
                     ({'label': 'Configure',
                       'action': 'manage_configure'},)
    
    manage_configure = PageTemplateFile('management/main.zpt',
                                        globals(),
                                        __name__='manage_main')
    
    archive_options = ['not archived', 'plain text', 'with attachments']
    
    id_namespace = 'http://xwft.org/ns/mailinglistmanager'
    _properties = (
        {'id':'title', 'type':'string', 'mode':'w'},
        {'id':'maillist', 'type':'lines', 'mode':'wd'},
        {'id':'disabled', 'type':'lines', 'mode':'wd'},
        {'id':'moderator', 'type':'lines', 'mode':'wd'},
        {'id':'moderatedlist', 'type':'lines', 'mode':'wd'},
        {'id':'mailoptions', 'type':'lines', 'mode':'wd'},
        {'id':'returnpath','type':'string', 'mode':'wd'},
        {'id':'moderated', 'type':'boolean', 'mode':'wd'},
        {'id':'unclosed','type':'boolean','mode':'wd'},
        {'id':'plainmail', 'type':'boolean', 'mode':'wd'},
        {'id':'keepdate', 'type':'boolean', 'mode':'wd'},
        {'id':'storage', 'type':'string', 'mode':'wd'},
        {'id':'archived', 'type':'selection','mode':'wd',
                      'select_variable':'archive_options'},
        {'id':'subscribe', 'type':'string', 'mode':'wd'},
        {'id':'unsubscribe','type':'string', 'mode':'wd'},
        {'id':'mtahosts', 'type':'tokens', 'mode':'wd'},
        {'id':'spamlist', 'type':'lines', 'mode':'wd'},
        {'id':'atmask', 'type':'string', 'mode':'wd'},
        {'id':'sniplist', 'type':'lines', 'mode':'wd'},
        {'id':'catalog', 'type':'string', 'mode':'wd'},
        {'id':'xmailer', 'type':'string', 'mode':'wd'},
        {'id':'headers', 'type':'string', 'mode':'wd'},
        {'id':'senderlimit','type':'int','mode':'wd'},
        {'id':'senderinterval','type':'int','mode':'wd'},
        {'id':'mailqueue','type':'string','mode':'wd'},
        {'id':'getter','type':'string','mode':'wd'},
        {'id':'setter','type':'string','mode':'wd'},
       )
    
    # initial properties, very handy when upgrading
    maillist = []
    disabled = []
    moderator = []
    moderatedlist = []
    mailoptions = []
    returnpath = ''
    moderated = 0
    unclosed = 0
    plainmail = 0
    keepdate = 0
    storage = 'archive'
    archived = archive_options[0]
    subscribe = 'subscribe'
    unsubscribe = 'unsubscribe'
    mtahosts = []
    spamlist = []
    atmask = '(at)'
    sniplist = [r'(\n>[^>].*)+|(\n>>[^>].*)+',
                r'(?s)\n-- .*',
                r'(?s)\n_+\n.*']
    catalog = 'Catalog'
    xmailer = 'GroupServer'
    headers = ''
    senderlimit = 10                # default: no more than 10 mails
    senderinterval = 600            # in 10 minutes (= 600 seconds) allowed
    mailqueue = 'mqueue'
    getter = ''
    setter = ''
        
    def __init__(self, id, title=''):
        """ Initialise a new instance of XWFMailingListManager.
        
        """
        self.__name__ = id
        self.id = id
        self.title = title
        self._setupMetadata()
        self.__initialised = 0
        
       
    security.declareProtected('Add Mail Boxers','manage_afterAdd') 
    def manage_afterAdd(self, item, container):
        """ For configuring the object post-instantiation.
                        
        """
        if getattr(self, '__initialised', 1):
            return 1
        
        return True

    security.declareProtected('View','get_catalog')
    def get_catalog(self):
        """ Get the catalog associated with this file library.
        
        """
        return self.Catalog

    security.declareProtected('View','find_email')
    def find_email(self, query):
        """ Return the catalog 'brains' objects representing the results of
        our query.
        
        """
        catalog = self.get_catalog()
        
        return catalog.searchResults(query)

    security.declareProtected('Manage properties', 'unrestricted_find_email')
    def unrestricted_find_email(self, query):
        """ Similar to find email, but using the unrestricted version of
        searchResults.
        
        """
        catalog = self.get_catalog()
        
        return catalog.unrestrictedSearchResults(query)

    security.declareProtected('View','get_list')
    def get_list(self, list_id):
        """ Get a contained list, given the list ID.
        
        """
        try:
            return getattr(self.aq_explicit, list_id)
        except AttributeError:
            raise AttributeError("No such list %s" % list_id)

    @cache('Products.XWFMailingListManager', lambda x,y: x, 3600)
    def get_listFromMailto(self, mailto):
        """ Get a contained list, given the list mailto.
        
        """
        mailto = mailto.lower()

        site = self.site_root()
        siteId = site.getId()

        # then try to find it fast, using the LHS of the email address
        listIds = self.objectIds('XWF Mailing List')
            
        assert mailto.find('@'), "No LHS/RHS with @ in mailto"

        possibleId = mailto.split('@')[0]
        possListIds = filter(None,
                      [x.find(possibleId) >= 0 and x for x in listIds])
        for listId in possListIds:
            listObj = getattr(self, listId)
            list_mailto = getattr(listObj, 'mailto', '').lower()
            if list_mailto:
                if list_mailto == mailto:
                    found = True
                    break
        
        # if we still haven't found it, wade through everything
        if not found:
            for listobj in self.objectValues('XWF Mailing List'):
                list_mailto = getattr(listobj, 'mailto', '').lower()
                listId = listobj.getId()
                if list_mailto:
                    if list_mailto == mailto:
                        log.debug("found list (%s) from mailto (%s) by slow lookup" % (listId, mailto))
                        found = True
                        break
        
        if not found:
            listId = ''
            log.warn("did not find list from mailto (%s)" % mailto)
                        
        return self.get_list(listId)

    security.declareProtected('View','get_listPropertiesFromMailto')
    def get_listPropertiesFromMailto(self, mailto):
        """ Get a contained list's properties, given the list mailto.
        
        """
        list_props = {}
        try:
            listobj = self.get_listFromMailto(mailto)
        except AttributeError:
            log.info("Could not find list for mailto (%s)" % mailto)
            listobj = None
        if listobj:
            for prop in self._properties:
                pid = prop['id']
                list_props[pid] = getattr(listobj, pid, None)
            list_props['id'] = listobj.getId()
            
        return list_props

    security.declareProtected('View','get_listProperty')
    def get_listProperty(self, list_id, property, default=None):
        """ Get the given property of the given list_id.
        
        """
        list = self.get_list(list_id)
            
        return list.getProperty(property, default)

    def processDigests(self, REQUEST):
        """ Process the digests for all lists.

        """
        messageQuery = MessageQuery(self)
        digestQuery = DigestQuery(self)

        # get the groups which have been active in the last 24-ish hours
        active_groups = messageQuery.active_groups() 
        
        # collect a dict of groups we want to digest
        digest_dict = {}
        for g in active_groups:
            digest_dict[(g['site_id'],g['group_id'])] = 1

        # get the groups which have *not* had a digest in the last 7-ish days,
        # but have been active in last 3 months
        no_recent_digest = digestQuery.no_digest_but_active()
        no_recent_digest_dict = {}        
        for g in no_recent_digest:
            key = (g['site_id'],g['group_id'])
            digest_dict[key] = 1
        
        digests_required = digest_dict.keys()

        for site_id,group_id in digests_required:
            log.info("Requesting digest for: %s, %s" % (site_id,group_id))
            group = self.get_list(group_id)
            if not group:
                log.warn("Could not find list: %s" % group_id)
                continue
            try:
                group.manage_digestBoxer(REQUEST)
            except Exception,x:
                fp = StringIO.StringIO()
                traceback.print_exc(file=fp)
                message = fp.getvalue()

                log.warn("Problems processing digest for list %s: %s" % (group_id, message))
                continue
            

    def processBounce(self, groupId, email):
        """ Process a bounce for a particular list.
        """
        try:
            mlist = self.get_list(groupId)
        except AttributeError:
            m = 'Bounce detection failure: no list for group id %s' % groupId
            log.warn(m)
            return m
        
        siteId = mlist.getProperty('siteId', '')
        group = get_group_by_siteId_and_groupId(mlist, siteId, groupId)
        groupInfo = IGSGroupInfo(group)
        siteInfo = createObject('groupserver.SiteInfo', group)
        context = groupInfo.groupObj

        user = self.acl_users.get_userByEmail(email)
        if not user:
            m = 'Bounce detection failure: no user with email <%s>' % email
            log.warn(m)
            return m
        userInfo = IGSUserInfo(user)

        bq = BounceQuery(context)
        previousBounceDates, daysChecked = bq.previousBounceDates(email)
        bq.addBounce(userInfo.id, groupInfo.id, siteInfo.id, email)
        auditor = BounceHandlingAuditor(context, userInfo, groupInfo, siteInfo)
        auditor.info(BOUNCE, email)

        doNotification = False
        now = datetime.datetime.now()
        bounceDate = now.strftime("%Y%m%d")
        if bounceDate not in previousBounceDates:
            previousBounceDates.append(bounceDate)
            doNotification = True

        emailUser = EmailUser(context, userInfo)
        addresses = [e.lower() for e in emailUser.get_verified_addresses()]
        try:
            addresses.remove(email.lower())
        except ValueError:
            m = u'%s (%s) <%s> was already unverified' %\
                 (userInfo.name, userInfo.id, email)
            m.encode('ascii', 'ignore')
            log.info(m)
            return True

        nType = 'bounce_detection'        
        numBounceDays = len(previousBounceDates)
        # After 5 bounces on unique days, disable address by unverifying
        if numBounceDays >= 5:
            uq = UserQuery(userInfo.user)
            uq.unverify_userEmail(email)
            stats = '%d;%d' % (numBounceDays, daysChecked)
            auditor.info(DISABLE, email, stats)
            nType = 'disabled_email'
        
        if doNotification and addresses:
            nDict =  {
              'userInfo'      : userInfo,
              'groupInfo'     : groupInfo,
              'siteInfo'      : siteInfo,
              'supportEmail'  : get_support_email(groupInfo.groupObj, siteInfo.id),
              'bounced_email' : email
            }
            try:
                notifyUser = NotifyUser(userInfo.user, siteInfo)
                notifyUser.send_notification(nType, groupInfo.id, nDict, addresses)
            except:
                m = 'Failed to send %s notification to %s' %\
                  (nType, addresses)
                log.warn(m)
        return True
                
manage_addXWFMailingListManagerForm = PageTemplateFile(
    'management/manage_addXWFMailingListManagerForm.zpt',
    globals(),
    __name__='manage_addXWFMailingListManagerForm')

def manage_addXWFMailingListManager(self, id, title='Mailing List Manager',
                                     REQUEST=None):
    """ Add an XWFMailingListManager to a container.

    """
    ob = XWFMailingListManager(id, title)
    self._setObject(id, ob)
    if REQUEST is not None:
        return self.manage_main(self,REQUEST)

InitializeClass(XWFMailingListManager)

def initialize(context):
    context.registerClass(
        XWFMailingListManager,
        permission="Add XWF MailingListManager",
        constructors=(manage_addXWFMailingListManagerForm,
                      manage_addXWFMailingListManager),
        icon='icons/ic-mailinglistmanager.png'
        )
