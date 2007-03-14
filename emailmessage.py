import re
import md5
import sqlalchemy
import string
import datetime

from email import Parser, Header
from rfc822 import AddressList

from zope.interface import Interface, Attribute, implements

from zope.app.datetimeutils import parseDatetimetz

def convert_int2b(num, alphabet, converted=[]):
    mod = num % len(alphabet); rem = num / len(alphabet)
    converted.append(alphabet[mod])
    if rem:
        return convert_int2b(rem, alphabet, converted)
    converted.reverse()

    return ''.join(converted)

def convert_int2b62(num):
    alphabet = string.printable[:62]
    
    return convert_int2b(num, alphabet, [])

def parse_disposition(s):
    matchObj = re.search('(?i)filename="*(?P<filename>[^"]*)"*', s)
    name = ''
    if matchObj:
        name = matchObj.group('filename')
    return name

def strip_subject(subject, list_title, remove_re=True):
    """ A helper function for tidying the subject line.

    """
    # remove the list title from the subject
    subject = re.sub('\[%s\]' % re.escape(list_title), '', subject).strip()
    
    # compress up the whitespace into a single space
    subject = re.sub('\s+', ' ', subject).strip()
    
    # remove the "re:" from the subject line. There are probably other variants
    # we don't yet handle.
    if subject.lower().find('re:', 0, 3) == 0 and len(subject) > 3:
        subject = subject[3:].strip()
    elif len(subject) == 0:
        subject = 'No Subject'
    
    return subject

def normalise_subject(subject):
    """ Compress whitespace and lower-case subject 
        
    """
    return re.sub('\s+', '', subject).lower()

def calculate_file_id(file_body, mime_type):
    # --=mpj17=--  
    # Two files will have the same ID if
    # - They have the same MD5 Sum, and
    # - They have the same length, and
    # - They have the same MIME-type.
    length = len(file_body)
    
    md5_sum = md5.new()
    for c in file_body:
        md5_sum.update(c)
    
    file_md5 = md5_sum.hexdigest()
    
    md5_sum.update(':'+str(length)+':'+mime_type)

    return (unicode(convert_int2b62(long(md5_sum.hexdigest(), 16))), length, file_md5)

class IRDBStorageForEmailMessage(Interface):
    pass

class RDBEmailMessageStorage(object): 
    implements(IRDBStorageForEmailMessage)
    
    def __init__(self, email_message):
        self.email_message = email_message

    def set_zalchemy_adaptor(self, da):
        session = da.getSession()
        metadata = session.getMetaData()
        
        self.postTable = sqlalchemy.Table('post', metadata, autoload=True)
        self.topicTable = sqlalchemy.Table('topic', metadata, autoload=True)
        self.topic_word_countTable = sqlalchemy.Table('topic_word_count', metadata, autoload=True)
        self.fileTable = sqlalchemy.Table('file', metadata, autoload=True)

    def _get_topic(self):
        and_ = sqlalchemy.and_; or_ = sqlalchemy.or_

        r = self.topicTable.select(and_(self.topicTable.c.topic_id == self.email_message.topic_id, 
                                        self.topicTable.c.group_id == self.email_message.group_id, 
                                        self.topicTable.c.site_id == self.email_message.site_id)).execute()
        
        return r.fetchone()

    def insert(self):
        and_ = sqlalchemy.and_; or_ = sqlalchemy.or_

        i = self.postTable.insert()
        i.execute(post_id=self.email_message.post_id, 
                   topic_id=self.email_message.topic_id, 
                   group_id=self.email_message.group_id, 
                   site_id=self.email_message.site_id, 
                   user_id=self.email_message.sender_id, 
                   in_reply_to=self.email_message.inreplyto, 
                   subject=self.email_message.subject, 
                   date=self.email_message.date, 
                   body=self.email_message.body, 
                   html_body=self.email_message.html_body, 
                   header=self.email_message.headers, 
                   has_attachments=bool(self.email_message.attachment_count))
        
        topic = self._get_topic()
        if not topic:
            i = self.topicTable.insert()
            i.execute(topic_id=self.email_message.topic_id, 
                       group_id=self.email_message.group_id, 
                       site_id=self.email_message.site_id, 
                       original_subject=self.email_message.subject, 
                       first_post_id=self.email_message.post_id, 
                       last_post_id=self.email_message.post_id, 
                       last_post_date=self.email_message.date, 
                       num_posts=1)
        else:
            num_posts = topic['num_posts']
            self.topicTable.update(and_(self.topicTable.c.topic_id == self.email_message.topic_id, 
                                         self.topicTable.c.group_id == self.email_message.group_id, 
                                         self.topicTable.c.site_id == self.email_message.site_id)
                                   ).execute(num_posts=num_posts+1, 
                                              last_post_id=self.email_message.post_id, 
                                              last_post_date=self.email_message.date)

        counts = self.email_message.word_count
        for word in counts:
            r = self.topic_word_countTable.select(and_(self.topic_word_countTable.c.topic_id == self.email_message.topic_id, 
                        self.topic_word_countTable.c.word == word)).execute().fetchone() 
            if r:
                self.topic_word_countTable.update(and_(self.topic_word_countTable.c.topic_id == self.email_message.topic_id, 
                        self.topic_word_countTable.c.word == word)).execute(count=r['count']+counts[word])
            else:
                i = self.topic_word_countTable.insert()
                i.execute(topic_id=self.email_message.topic_id, 
                           word=word, 
                           count=counts[word])
                           
    def remove(self):
        and_ = sqlalchemy.and_; or_ = sqlalchemy.or_
        topic = self._get_topic()
        if topic['num_posts'] == 1:
            self.topicTable.delete(self.topicTable.c.topic_id == self.email_message.topic_id).execute()         

        #self.topicTable.update( self.topicTable.c.first_post_id == self.email_message.post_id ).execute( first_post_id='' )
        #self.topicTable.update( self.topicTable.c.last_post_id == self.email_message.post_id ).execute( last_post_id='' )
        self.postTable.delete(self.postTable.c.post_id == self.email_message.post_id).execute()    

class IEmailMessage(Interface):
    """ A representation of an email message.
    
    """
    post_id = Attribute("The unique ID for the post, based on attributes of the message")
    topic_id = Attribute("The unique ID for the topic, based on attributes of the message")
    
    encoding = Attribute("The encoding of the email and headers.")
    attachments = Attribute("A list of attachment payloads, each structured "
                            "as a dictionary, from the email (both body and "
                            "attachments).")
    body = Attribute("The plain text body of the email message.")
    html_body = Attribute("The html body of the email message, if one exists")
    subject = Attribute("Get the subject of the email message, stripped of "
                        "additional details (such as re:, and list title)")
    compressed_subject = Attribute("Get the compressed subject of the email "
                                  "message, with all whitespace removed.")
    
    sender_id = Attribute("The user ID of the message sender")
    headers = Attribute("A flattened version of the email headers")
    language = Attribute("The language in which the email has been composed")
    inreplyto = Attribute("The value of the inreplyto header if it exists")
    date = Attribute("The date on which the email was sent")
    md5_body = Attribute("An md5 checksum of the plain text body of the email")
    
    to = Attribute("The email address the message was sent to")
    sender = Attribute("The email address the message was sent from")
    title = Attribute("An attempt at a title for the email")
    
    attachment_count = Attribute("A count of attachments which have a filename")
    word_count = Attribute("A dictionary of words and their count within the document")
    
    def get(name, default): #@NoSelf
        """ Get the value of a header, changed to unicode using the
            encoding of the email.
        
        @param name: identifier of header, eg. 'subject'
        @param default: default value, if header does not exist. Defaults to '' if
            left unspecified
        """

class EmailMessage(object):
    implements(IEmailMessage)

    def __init__(self, message, list_title='', group_id='', site_id='', sender_id_cb=None):
        parser = Parser.Parser()
        msg = parser.parsestr(message)
        
        self.message = msg
        self._list_title = list_title
        self.group_id = group_id
        self.site_id = site_id
        self.sender_id_cb = sender_id_cb
        
    def get(self, name, default=''):
        value = self.message.get(name, default)
        value, encoding = Header.decode_header(value)[0]
        
        value = unicode(value, encoding or self.encoding, 'ignore')
        
        return value

    @property
    def sender_id(self):
        if self.sender_id_cb:
            return self.sender_id_cb( self.sender )
        
        return ''
    
    @property
    def encoding(self):
        return self.message.get_param('charset', 'ascii')

    @property
    def attachments(self):
        def split_multipart(msg, pl):
            if msg.is_multipart():
                for b in msg.get_payload():
                    pl = split_multipart(b, pl)
            else:
                pl.append(msg)
            
            return pl           

        payload = self.message.get_payload()
        if isinstance(payload, list):
            outmessages = []
            out = []
            for i in payload:
                outmessages = split_multipart(i, outmessages)
                    
            for msg in outmessages:
                actual_payload = msg.get_payload(decode=True)
                
                filename = unicode(parse_disposition(msg.get('content-disposition', '')), 
                                    self.encoding, 'ignore')
                fileid, length, md5_sum = calculate_file_id(actual_payload, msg.get_content_type())
                out.append({'payload': actual_payload, 
                             'fileid': fileid, 
                             'filename': filename, 
                             'length': length, 
                             'md5': md5_sum, 
                             'charset': msg.get_charset(), 
                             'maintype': msg.get_content_maintype(), 
                             'subtype': msg.get_content_subtype(), 
                             'mimetype': msg.get_content_type(), 
                             'contentid': msg.get('content-id', '')})
            return out
        else:
            # since we aren't a bunch of attachments, actually decode the body
            payload = self.message.get_payload(decode=True)
            
        filename = unicode(parse_disposition(self.message.get('content-disposition', '')), 
                            self.encoding, 'ignore')
        
        fileid, length, md5_sum = calculate_file_id(payload, self.message.get_content_type())
        return [ {'payload': payload, 
                  'md5': md5_sum, 
                  'fileid': fileid, 
                  'filename': filename, 
                  'length': length, 
                  'charset': self.message.get_charset(), 
                  'maintype': self.message.get_content_maintype(), 
                  'subtype': self.message.get_content_subtype(), 
                  'mimetype': self.message.get_content_type(), 
                  'contentid': self.message.get('content-id', '')}
               ]

    @property
    def headers(self):
        # return a flattened version of the headers
        header_string = '\n'.join(map(lambda x: '%s: %s' % (x[0], x[1]), self.message._headers))
        return unicode(header_string, self.encoding, 'ignore')

    @property
    def attachment_count(self):
        count = 0
        for item in self.attachments:
            if item['filename']:
                count += 1
        
        return count

    @property
    def language(self):
       # one day we might want to detect languages, primarily this
       # will be used for stemming, stopwords and search
       return 'en'
    
    @property
    def word_count(self):
        wc = {}
        for word in self.body.split():
            word = word.lower()
            skip = False
            if len(word) < 3 or len(word) > 18:
                continue
            for letter in word:
                if letter not in string.ascii_lowercase:
                    skip = True
                    break
            if skip:
                continue
            
            if wc.has_key(word):
                wc[word] += 1
            else:
                wc[word] = 1
        
        return wc

    @property
    def body(self):
        for item in self.attachments:
            if item['filename'] == '' and item['subtype'] != 'html':
                return unicode(item['payload'], self.encoding, 'ignore')
        return ''

    @property
    def html_body(self):
        for item in self.attachments:
            if item['filename'] == '' and item['subtype'] == 'html':
                return unicode(item['payload'], self.encoding, 'ignore')
        return ''

    @property
    def subject(self):
        return strip_subject(self.get('subject'), self._list_title)

    @property
    def compressed_subject(self):
        return normalise_subject(self.subject)

    @property
    def sender(self):
        sender = self.get('from')
        
        if sender:
            name, sender = AddressList(sender)[0]
        
        return sender

    @property
    def to(self):
        to = self.get('to')
        
        if to:
            name, to = AddressList(to)[0]
        
        return to

    @property
    def title(self):
        return '%s / %s' % (self.subject, self.sender)

    @property
    def inreplyto(self):
        return self.get('in-reply-to')

    @property
    def date(self):
        d = self.get('date', '').strip()
        if d:
            return parseDatetimetz(d)
        
        return datetime.datetime.now()        

    @property
    def md5_body(self):
        return md5.new(self.body).hexdigest()
    
    @property
    def topic_id(self):
        # this is calculated from what we have/know
        
        # A topic_id for two posts will clash if
        #   - The compressedsubject, group ID and site ID are all identical
        items = self.compressed_subject + ':' + self.group_id + ':' + self.site_id
        tid = md5.new(items).hexdigest()
        
        return unicode(convert_int2b62(long(tid, 16)))
        
    @property
    def post_id(self):
        # this is calculated from what we have/know
        len_payloads = sum([ x['length'] for x in self.attachments ])
        
        # A post_id for two posts will clash if
        #    - The topic IDs are the same, and
        #    - The subject is the same (this may not be the same as 
        #      compressed subject used in topic id)
        #    - The body of the posts are the same, and
        #    - The posts are from the same author, and
        #    - The posts respond to the same message, and
        #    - The posts have the same length of attachments.
        items = (self.topic_id + ':' + self.subject + ':' +
                  self.md5_body + ':' + self.sender + ':' + 
                  self.inreplyto + ':' + str(len_payloads))
        pid = md5.new(items).hexdigest()
        
        return unicode(convert_int2b62(long(pid, 16)))
