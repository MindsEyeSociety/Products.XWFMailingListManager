# Copyright IOPEN Technologies Ltd., 2003
# richard@iopen.net
#
# For details of the license, please see LICENSE.
#
# You MUST follow the rules in README_STYLE before checking in code
# to the head. Code which does not follow the rules will be rejected.  
#
import os, Globals

from Products.PageTemplates.PageTemplateFile import PageTemplateFile
from Products.XWFIdFactory.XWFIdFactoryMixin import XWFIdFactoryMixin

from AccessControl import getSecurityManager, ClassSecurityInfo
from types import *
from Globals import InitializeClass, PersistentMapping
from OFS.Folder import Folder
from Products.XWFCore.XWFUtils import createBatch
from zLOG import LOG, WARNING, PROBLEM, INFO

class XWFVirtualListError(Exception):
    pass


class XWFVirtualMailingListArchive(Folder, XWFIdFactoryMixin):
    """ A folder for virtualizing mailing list content.
        
    """
    security = ClassSecurityInfo()
    
    meta_type = 'XWF Virtual Mailing List Archive'
    version = 0.1
    
    manage_options = Folder.manage_options + \
                     ({'label': 'Configure',
                       'action': 'manage_configure'},)
        
    #id_factory = 'IdFactory'
    #id_namespace = 'http://xwft.org/namespaces/xwft/virtualfolder'
    
    default_nsprefix = 'list'
    
    _properties=(
        {'id':'title', 'type':'string', 'mode':'w'},
        {'id':'id_factory', 'type':'string', 'mode':'w'},
        {'id':'xwf_mailing_list_manager_path', 'type':'string', 'mode':'w'},
        {'id':'xwf_mailing_list_ids', 'type':'lines', 'mode':'w'},
                )
    
    def __init__(self, id, title=None):
        """ Initialise a new instance of XWFVirtualMailingListManager.
            
        """
        self.__name__ = id
        self.id = id
        self.title = title or id
        self.xwf_mailing_list_manager_path = ''
        self.xwf_mailing_list_ids = []

    def manage_afterAdd(self, item, container):
        """ For configuring the object post-instantiation.
            
        """
        # note that the UCID is a string
        #self.ucid = str(self.get_nextId())
        
    def get_xwfMailingListManager(self):
        """ Get the reference to the xwfMailingListManager we are associated with.
        
        """
        if not self.xwf_mailing_list_manager_path:
            raise XWFVirtualListError, 'Unable to retrieve list manager, no path set'
            
        return self.restrictedTraverse(self.xwf_mailing_list_manager_path)

    def get_listProperty(self, list_id, property, default=None):
        """ Get the given property of a given list or return the default.
        
        """
        if list_id not in self.xwf_mailing_list_ids:
            raise (XWFVirtualListError,
                  'Unable to retrieve list_id %s, list not registered' % list_id)
        list_manager = self.get_xwfMailingListManager()
        
        return list_manager.get_listProperty(list_id, property, default)

    def get_xml(self, set_top=0):
        """ Generate an XML representation of this folder.
        
        """
        xml_stream = ['<%s:folder rdf:id="%s" %s:top="%s"' % (
                                                   self.default_nsprefix,
                                                   self.getId(),
                                                   self.default_nsprefix,
                                                   set_top)]
        xa = xml_stream.append
        
        xa('xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">')
        
        xa('</%s:folder>' % self.default_nsprefix)
    
        return '\n'.join(xml_stream)
    
    security.declareProtected('View', 'find_email')
    def find_email(self, query={}):
        """ Perform a search against the email associated with this 
            VirtualMailingListArchive.
            
            Takes:
              query: a catalog query dictionary
              
           The results returned act as a lazy sequence, from the ZCatalog.Lazy
           module, so it is possible to slice the returned sequence in order to
           limit the result set.
           
           It is possible to sort the result set using the sort_on, sort_order
           and sort_limit index names in the query dictionary. See the ZCatalog
           documentation for further information on the query dictionary.
           
        """
        list_manager = self.get_xwfMailingListManager()

        mlids = filter(None, self.xwf_mailing_list_ids)
        if mlids:
            query['listId'] = mlids
        
        if list_manager.meta_type == 'XWF Virtual Mailing List Archive':
            raise (XWFVirtualListError, 
            'Caught potential recursion, mailing list archive is a virtual list archive')
        
        # we use an unrestricted find, so that our search is based on the
        # access to this find_email
        return list_manager.unrestricted_find_email(query)

    # get_email is protected by the security of find_email
    def get_email(self, id):
        """ Get an email given its unique identifier.
        
        """
        object = self.find_email({'id': id})[0].getObject()
        
        return object

    #   
    # Views and Workflow
    #
    def index_html(self):
        """ Return the default view.
        
        """
        presentation = self.Presentation.Tofu.MailingListManager.xml
        
        return presentation.default()

    def send_email(self, REQUEST, RESPONSE,
                   group_id, email_address,  email_id,  message, 
                   subject=''):
        """ Send an email to the group.
            
        """
        list_manager = self.get_xwfMailingListManager()
        
        sec = getSecurityManager()
        user = sec.getUser()
        if email_address not in user.get_emailAddresses():
            raise 'Forbidden', 'Only the authenticated owner of an email address may use it to post'
        
        group = getattr(list_manager, group_id)

        blocked_members = group.getProperty('blocked_members')
        if blocked_members and user.getId() in blocked_members:
            message = 'Blocked user: %s from posting via web' % user.getId()
            LOG('XWFVirtualMailingListArchive', PROBLEM, message)
            raise 'Forbidden', 'You are currently blocked from posting. Please contact the group administrator'
        
        moderatedlist = group.getValueFor('moderatedlist')
        moderated = group.getValueFor('moderated')
        via_mailserver = False
        # if we are moderated _and_ we have a moderatedlist, only users in the moderated list are moderated
        if moderated and moderatedlist:
            for address in user.get_emailAddresses():
                if address in moderatedlist:
                    LOG('XWFVirtualMailingListArchive', INFO, 'User "%s" posted from web while moderated' % user.getId())
                    via_mailserver = True
                    break
        # otherwise if we are moderated, everyone is moderated
        elif moderated:
              LOG('XWFVirtualMailingListArchive', INFO, 'User "%s" posted from web while moderated' % user.getId())
              via_mailserver = True
        
        group_email = group.getProperty('mailto')
        group_name = group.getProperty('title')
        
        message_id = None
        if email_id:
            orig_email = self.get_email(email_id)
            subject = 'Re: %s' % orig_email.getProperty('mailSubject')
            message_id = orig_email.getProperty('message-id', '')
            
        name = '%s %s' % (user.preferredName, user.lastName)
        
        headers = """From: %s <%s>
To: %s <%s>
Subject: %s
""" % (name, email_address, group_name, group_email, subject)

        if message_id:
            headers += """In-Reply-To: %s
""" % (message_id,)

        message = """%s

%s""" %  (headers, message)

        if via_mailserver:
            list_manager.MailHost.send(message)
        else:
            group.manage_listboxer({'Mail': message})

        return RESPONSE.redirect('view_threads')
        
    def view_send_email(self, id=None):
        """ Return the email sending view.
        
        """
        presentation = self.Presentation.Tofu.MailingListManager.xml
        
        if id:
            email_object = self.get_email(id)
        else:
            email_object = None
            
        return presentation.sendemail(email_object=email_object)
        
    def view_email(self, id, show_thread=0):
        """Return the email view.

        ARGUMENTS
        "id": The interger identifier of an *email* message, which is
          used as the basis of the search. The "thread" is the list of
          all messages with the same subject as the message "id".
        "show_thread": Whether to show all the thread details or not,
          as a boolean (defaults to False).

        RETURNS
          An XML Presentation instance for the thread, with three
          arguments passed in as part of the "options" dictionary:
           * "result_set", the list of email messages,
           * "previous", the temporally-previous thread, as a 2-tuple
             of thread ID and thread name, and
           * "next", the temporally-next thread, as a 2-tuple
             of thread ID and thread name.
             
        SIDE EFFECTS
          None
        """
        from DocumentTemplate import sequence
        presentation = self.Presentation.Tofu.MailingListManager.xml

        email_object = self.get_email(id)
        
        if show_thread:
            q_dict = {'compressedTopic': '%s' % email_object.compressedSubject}
            result_set = map(lambda x: x.getObject(),
                             self.find_email(query=q_dict))
            
            # We probably did really well with the exact phrase
            #   search, but we need to be bang on 
            result_set = filter(lambda x: x and x.compressedSubject.lower() == 
                                email_object.compressedSubject.lower(),
                                result_set)
            result_set = sequence.sort(result_set, (('mailDate',
                                                     'cmp', 'asc'), 
                                                    ('mailSubject',
                                                     'nocase',
                                                     'asc')))
            # Get the previous and next threads
            subjectQuery = {'mailSubject' : email_object.mailSubject}
            previous, next = \
                      self.get_previous_next_threads(subjectQuery,
                                                     s_on='mailDate',
                                                     s_order='asc')
        else:
            result_set = (email_object,)
            subjectQuery = {'mailSubject' : email_object.mailSubject}
            previous, next = \
                      self.get_previous_next_threads(subjectQuery,
                                                     s_on='mailDate',
                                                     s_order='asc')
        
        return presentation.email(result_set=result_set,
                                  previous=previous, next=next)

    def get_previous_next_threads(self, REQUEST, s_on, s_order):
        """Get the threads that are temporally before and after the
        current thread

        ARGUMENTS
          * "REQUEST" the request dictionary, which is used as a query
            dictionary.
          * "s_on" what to sort on: 'mailDate', 'mailSubject' or
            'mailCount'.
          * "s_order" the sort order for the list, where 'asc' is
            ascending.

        RETURNS
          A 2-tuple of the previous and next threads, or None if the
          thread do not exist. Each thread is a 2-tuple of the thread
          ID and the thread subject.
          
        SIDE EFFECTS
          None.
        """
        previous = None
        next = None

        # Get all the thread names.
        threads = self.get_all_threads({}, s_on, s_order)
        threadNames = map(lambda thread: thread[1][0]['mailSubject'],
                          threads)

        # Find the current thread
        currentThreadName = REQUEST['mailSubject']

        # If the current thread is not in the list of threads, then we
        #   have problems, but I am a defensive coder.
        if currentThreadName in threadNames:
            # Get the next and previous threads.
            currentThreadIndex = threadNames.index(currentThreadName)

            previousIndex = currentThreadIndex - 1
            if previousIndex >= 0:
                previousSubject = threads[previousIndex][1][0]['mailSubject']
                previousId = threads[previousIndex][1][0]['id']
                previous = (previousId, previousSubject)
                
            nextIndex = currentThreadIndex + 1
            if nextIndex < len(threads):
                nextSubject = threads[nextIndex][1][0]['mailSubject']
                nextId = threads[nextIndex][1][0]['id']
                next = (nextId, nextSubject)

        return (previous, next)

    def get_all_threads(self, REQUEST, s_on, s_order):
        """Get all the threads associated with the email archive

        ARGUMENTS
          * "REQUEST" The HTTP request object, which is used as a
            query dictionary.
          * "s_on" What to sort on: 'mailDate', 'mailSubject' or
            'mailCount'.
          * "s_order" The sort order for the list, where 'asc' is
            ascending.

        RETURNS
          The list of threads.

        SIDE EFFECTS
          None.
        """
        from DocumentTemplate import sequence
        def thread_sorter(a, b):
            if s_on in ('mailDate', 'mailSubject'):
                a = getattr(a[1][0], s_on); b = getattr(b[1][0], s_on)
            elif s_on in ('mailCount', ):
                a = a[0]; b = b[0]
            else:
                return 0
                
            if not a > b: 
                return s_order == 'asc' and -1 or 1
            elif not a < b:
                return s_order == 'asc' and 1 or -1
            else:
                return 0 
        
        result_set = self.find_email(REQUEST)
        result_set = sequence.sort(result_set, (('mailSubject', 'nocase'),
                                                ('mailDate', 'cmp', 'desc')))
        threads = []
        curr_thread = None
        curr_thread_results = []
        thread_index = {}
        for result in result_set:
            if result.mailSubject.lower() == curr_thread: # existing thread
                curr_thread_results.append(result)
            else: # new thread
                if curr_thread_results:
                    if thread_index.has_key(curr_thread):
                        tr = list(threads[thread_index[curr_thread]][-1])
                        tr += curr_thread_results
                        threads[thread_index[curr_thread]] = (len(tr), tr)
                    else:
                        threads.append((len(curr_thread_results),
                                        curr_thread_results))
                        thread_index[curr_thread] = len(threads) - 1
                    
                curr_thread_results = [result]
                curr_thread = result.mailSubject.lower()

        if curr_thread_results:
            threads.append((len(curr_thread_results),
                            curr_thread_results))
                            
        threads.sort(thread_sorter)

        return threads
        
    def thread_results(self, REQUEST, b_start, b_size, s_on, s_order):
        """ Get a thread result set."""

        threads = self.get_all_threads(REQUEST, s_on, s_order)
        return createBatch(threads, b_start, b_size)
        
    def view_threads(self, REQUEST, b_start=1, b_size=20,
                     s_on='mailDate', s_order='desc'):
        """ Return the threaded view.
        
        """
        presentation = self.Presentation.Tofu.MailingListManager.xml
        presenter = getattr(presentation, 'threaded')
	
        (b_start, b_end, b_size, 
         result_size, result_set) = self.thread_results(REQUEST, b_start,
                                                        b_size, s_on,
                                                        s_order)
	
        return presenter(result_set=result_set,
                         b_start=b_start+1, b_size=b_size, b_end=b_end,
                         result_size=result_size)

    def view_thread_rss(self, REQUEST, b_start=1, b_size=20,
                        s_on='mailDate', s_order='desc'):
        """ Return the threaded view.
        
        """
        presentation = self.Presentation.Tofu.MailingListManager.xml
        presenter = getattr(presentation, 'threaded.rss')

        (b_start, b_end, b_size, 
         result_size, result_set) = self.thread_results(REQUEST,
                                                        b_start,
                                                        b_size, s_on,
                                                        s_order)
	
        return presenter(result_set=result_set,
                         b_start=b_start+1, b_size=b_size, b_end=b_end,
                         result_size=result_size)
        
    def view_search(self):
        """ Return the search view.
        
        """
        presentation = self.Presentation.Default.MailingListManager.xml
        
        return presentation.search()

    security.declarePublic('view_results')
    def view_results(self, REQUEST, b_start=1, b_size=20,
                     s_on='mailDate', s_order='desc',summary=1):
        """ Return the results view.
        
            Optionally specify the start and end point of the result set,
            term to sort on, and the sort order. Finally, a flag to indicate
            if a summary of the results should be shown, or not.
        
        """ 
        from DocumentTemplate import sequence
        presentation = self.Presentation.Tofu.MailingListManager.xml
        
        result_set = self.find_email(REQUEST)
        
        if s_on == 'mailDate':
            result_set = sequence.sort(result_set, (('mailDate',
                                                     'cmp', s_order),
                                                    ('mailSubject',
                                                     'nocase',
                                                     s_order)))
        else:
            result_set = sequence.sort(result_set, ((s_on, 'nocase', s_order),
                                                    ('mailDate',
                                                     'cmp', s_order)))
        
        (b_start, b_end, b_size, result_size,
         result_set) = createBatch(result_set, b_start, b_size)
        
        return presentation.results(result_set=result_set,
                                    b_start=b_start+1, b_size=b_size,
                                    b_end=b_end,
                                    result_size=result_size,
                                    resultsummary=summary)
        
    security.declareProtected('Upgrade objects', 'upgrade')
    security.setPermissionDefault('Upgrade objects', ('Manager', 'Owner'))
    def upgrade(self):
        """ Upgrade to the latest version.
            
        """
        currversion = getattr(self, '_version', 0)
        if currversion == self.version:
            return 'already running latest version (%s)' % currversion

        self._version = self.version
        
        return 'upgraded %s to version %s from version %s' % (self.getId(),
                                                              self._version,
                                                              currversion)


Globals.InitializeClass(XWFVirtualMailingListArchive)
#
# Zope Management Methods
#
manage_addXWFVirtualMailingListArchiveForm = PageTemplateFile(
    'management/manage_addXWFVirtualMailingListArchiveForm.zpt',
    globals(), __name__='manage_addXWFVirtualMailingListArchiveForm')

def manage_addXWFVirtualMailingListArchive(self, id, title=None,
                               REQUEST=None, RESPONSE=None, submit=None):
    """ Add a new instance of XWFVirtualMailingListArchive
        
    """
    obj = XWFVirtualMailingListArchive(id, title)
    self._setObject(id, obj)
    
    obj = getattr(self, id)
    
    if RESPONSE and submit:
        if submit.strip().lower() == 'add':
            RESPONSE.redirect('%s/manage_main' % self.DestinationURL())
        else:
            RESPONSE.redirect('%s/manage_main' % id)

def initialize(context):
    import os
    context.registerClass(
        XWFVirtualMailingListArchive,
        permission='Add XWF Virtual Mailing List Archive',
        constructors=(manage_addXWFVirtualMailingListArchiveForm,
                      manage_addXWFVirtualMailingListArchive)
    )
#        #icon='icons/ic-virtualfolder.png'
#        )
