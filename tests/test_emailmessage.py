##############################################################################
#
# Copyright (c) 2004, 2005 Zope Corporation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Size adapters for testing

$Id: test_size.py 61072 2005-10-31 17:43:51Z philikon $
"""
import os, sys
if __name__ == '__main__':
    execfile(os.path.join(sys.path[0], 'framework.py'))

from zope.interface import implements
from zope.app.size.interfaces import ISized

def test_emailmessage():
    """
    Test emailmessage and adapters

    Set up:
      >>> from zope.app.testing.placelesssetup import setUp, tearDown
      >>> setUp()
      >>> import time
      >>> import Products.Five
      >>> import Products.XWFMailingListManager
      >>> from Products.XWFMailingListManager import emailmessage
      >>> from Products.Five import zcml
      >>> from Products.ZSQLAlchemy.ZSQLAlchemy import manage_addZSQLAlchemy

      >>> zcml.load_config('meta.zcml', Products.Five)
      >>> zcml.load_config('permissions.zcml', Products.Five)
      >>> zcml.load_config('configure.zcml', Products.XWFMailingListManager)

      >>> email_attachments = file('emails/withattachments.eml').read()
      >>> email_b64attachments = file('emails/base64attachments.eml').read()
      >>> email_b64 = file('emails/base64.eml').read()
      >>> email_simple = file('emails/simple.eml').read()
      >>> email_simple2 = file('emails/simple2.eml').read()
      >>> email_test1 = file('emails/testemail1.eml').read()
      >>> email_attachments2 = file('emails/7479421AFD9.eml').read()
      >>> toptime = time.time()
      >>> msg = emailmessage.EmailMessage(email_attachments) 
      >>> msg.sender
      u'richard@iopen.net'
      >>> msg.subject
      u'testing attachments'
      >>> msg.title
      u'testing attachments / richard@iopen.net'
      >>> getattr(msg, 'title')
      u'testing attachments / richard@iopen.net'
      >>> msg.date.isoformat()
      '2007-02-26T16:53:19+13:00'
      >>> msg.post_id
      u'7Lx559UTM0RJtoDhmzapyJ'
      >>> msg.topic_id
      u'1Aa4fgicLuUNeXE6737X9K'
      >>> msg.inreplyto
      u''

   A second attachments example:
      >>> msg2 = emailmessage.EmailMessage(email_attachments2) 
      >>> [ a['filename'] for a in msg2.attachments ]
      [u'', u'', u'', u'', u'image003.jpg', u'image001.jpg', u'Christchurch City Flyer 2007-2008.doc']
      
   An email that has a base 64 attachment:
      >>> b64msg = emailmessage.EmailMessage(email_b64attachments) 
      >>> b64msg.attachments[1]['filename']
      u'Delivery report.txt'

   An email that has the entire body encoded as base64
      >>> b64msg = emailmessage.EmailMessage(email_b64)
      >>> b64msg.attachments[0]['md5']
      '3c56c82af9e6604d31afba86b083444a'

      >>> simplemsg = emailmessage.EmailMessage(email_simple, 'Example Group')
      >>> simplemsg.title
      u'testing 7 / richard@iopen.net'
      >>> simplemsg.sender
      u'richard@iopen.net'
      >>> simplemsg.message.get('from')
      '"" <richard@iopen.net>'

      >>> simplemsg2 = emailmessage.EmailMessage(email_simple2, 'Example Group')
      >>> simplemsg2.post_id == simplemsg.post_id
      False
      >>> simplemsg2.topic_id == simplemsg.topic_id
      True
     
      >>> test1msg = emailmessage.EmailMessage(email_test1)
      >>> test1msg.title
      u'Email bounced / privacy@obscured.co.nz'
      >>> test1msg.sender
      u'privacy@obscured.co.nz'
      >>> test1msg.message.get('from')
      'privacy@obscured.co.nz'
      >>> len(test1msg.headers)
      2281
      >>> test1msg.inreplyto
      u'<20070227111232.C25DDFFF1@orange.iopen.net>'
      >>> test1msg.word_count['message']
      4
      
    Setup ZSQLAlchemy
      >>> alchemy_adaptor = manage_addZSQLAlchemy(app, 'zalchemy')
      >>> alchemy_adaptor.manage_changeProperties( hostname='localhost',
      ...                                             port=5432,
      ...                                             username='richard',
      ...                                             password='',
      ...                                             dbtype='postgres',
      ...                                             database='onlinegroups.net')

    Adapt:
      >>> from Products.XWFMailingListManager.emailmessage import IRDBStorageForEmailMessage
      >>> msgstorage = IRDBStorageForEmailMessage( simplemsg )
      >>> msgstorage.set_zalchemy_adaptor( alchemy_adaptor )
      >>> msgstorage.insert()

      #>>> msgstorage.remove()

      >>> msgstorage2 = IRDBStorageForEmailMessage( b64msg )
      >>> msgstorage2.set_zalchemy_adaptor( alchemy_adaptor )
      >>> msgstorage2.insert()

      >>> msgstorage3 = IRDBStorageForEmailMessage( msg2 )
      >>> msgstorage3.set_zalchemy_adaptor( alchemy_adaptor )
      >>> msgstorage3.insert()

      #>>> msgstorage2.remove()
      >>> print time.time()-toptime

    Clean up:
      >>> tearDown()
      
    """

def test_suite():
    from Testing.ZopeTestCase import ZopeDocTestSuite
    return ZopeDocTestSuite()

if __name__ == '__main__':
    framework()
