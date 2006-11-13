import sys, re, datetime, time, types, string
import Products.Five, DateTime, Globals
#import Products.Five.browser.pagetemplatefile
import zope.schema
import zope.app.pagetemplate.viewpagetemplatefile
import zope.pagetemplate.pagetemplatefile
import zope.interface, zope.component, zope.publisher.interfaces
import zope.viewlet.interfaces, zope.contentprovider.interfaces 

import DocumentTemplate, Products.XWFMailingListManager

import Products.GSContent, Products.XWFCore.XWFUtils

# <zope-3 weirdness="high">
          
class GSPostContentProvider(object):
      """GroupServer Post Content Provider: display a single post
      
      This content provider, which implements the "IGSPostContentProvider"
      and "IContentProvider" interfaces, displays a single post. The post
      is specified by setting the "post" variable to an instance of an 
      email-object. The post-instance is examined, during the "update", to
      determine additional information, which is passed to the email 
      page-template during the "render" phase.
      
      EXAMPLE
         <p tal:define="post python:view.get_email()"
            tal:replace="structure provider:groupserver.Post">
            The email message is rendered by the Post content provider,
            not by this page.
         </p>
      """

      zope.interface.implements(Products.XWFMailingListManager.interfaces.IGSPostContentProvider)
      zope.component.adapts(zope.interface.Interface,
                            zope.publisher.interfaces.browser.IDefaultBrowserLayer,
                            zope.interface.Interface)
      post = None
      def __init__(self, context, request, view):
          """Create a GSPostContentProvider instance.
          
          Like any other content-provider class, the context, request and
          view are passed as arguments to "__init__". However, this is
          normally done by TAL, rather than explicitly by the coders.
          
          SIDE EFFECTS
            The following attributes are set.
              * "self.__parent"     Set to "view".
              * "self.__updated"    Set to "False"
              * "self.context"      Set to "context"
              * "self.request"      Set to "request"
              * "self.pageTemplate" Set to the hard-coded page template 
                                    object, which is used to render the 
                                    post.
              """
          self.__parent__ = self.view = view
          self.__updated = False
      
          self.context = context
          self.request = request
      
      def update(self):
          """Update the internal state of the post content-provider.
          
          This method can be considered the main "setter" for the 
          content provider; for the most part, information about the post's 
          author is set.
          
          SIDE EFFECTS
            The following attributes are set.
              * "self.__updated"     Set to "True"
              * "self.authorId"      Set to the user-id of the post author.
              * "self.authorName"    Set to the name of the post author.
              * "self.authorExists"  Set to "True" if the author exists
              * "self.authored"      Set to "True" if the current user 
                                     authored the post.
              * "self.authorImage"   Set to the URL of the author's image.
          """
          assert self.post
          
          self.__updated = True
          
          self.authorId = self.post.mailUserId;
          self.authorName = self.get_author_realnames();
          self.authorExists = self.author_exists();
          self.authored = self.authorExists and self.user_authored();
          self.authorImage = self.get_author_image()
         
          ir = self.get_email_intro_and_remainder()
          self.postIntro, self.postRemainder = ir
          
          self.cssClass = self.get_cssClass()
           
          assert self.__updated
          
      def render(self):
          """Render the post
          
          The donkey-work of this method is done by "self.pageTemplate", 
          which is set when the content-provider is created.
          
          RETURNS
              An HTML-snippet that represents the post."""
          if not self.__updated:
              raise interfaces.UpdateNotCalled
      
          VPTF = zope.pagetemplate.pagetemplatefile.PageTemplateFile
          pageTemplate = VPTF(self.pageTemplateFileName)

          return pageTemplate(authorId=self.authorId, 
                              authorName=self.authorName,
                              authorExists=self.authorExists,
                              authorImage=self.authorImage,
                              authored=self.authored,
                              postIntro=self.postIntro,
                              postRemainder=self.postRemainder,
                              cssClass=self.cssClass,
                              topicName=self.topicName,
                              post=self.post,
                              context=self.context,
                              siteName = self.siteInfo.get_name(),
                              siteURL = self.siteInfo.get_url(),
                              groupId = self.groupInfo.get_id())

      #########################################
      # Non-standard methods below this point #
      #########################################
          
      def __markup_text(self, messageText):
          """Mark up the plain text
          
          Used to mark up the email: the URLs are escaped, and "@"
          characters are  replaced with "( at )". 
          
          ARGUMENTS
              "messageText" The text to alter.
               
          RETURNS
              A string containing the marked-up text.
              
          SIDE EFFECTS
              None.

          NOTE    
              Originally found in XWFCore."""
          import re, cgi
          retval = ''
          
          text = cgi.escape(messageText)
          text = re.sub('(?i)(http://|https://)(.+?)(\&lt;|\&gt;|\)|\]|\}|\"|\'|$|\s)',
                 '<a href="\g<1>\g<2>">\g<1>\g<2></a>\g<3>',
                 text)
          retval = text.replace('@', ' ( at ) ')
         
          assert retval
          return retval
      
      def __wrap_message(self, messageText, width=79):
          """Word-wrap the message
          
          ARGUMENTS
              "messageText" The text to alter.
              "width"       The column-number which to wrap at.
              
          RETURNS
              A string containing the wrapped text.
              
          SIDE EFFECTS
              None.
              
          NOTE
              Originally a stand-alone script in
              "Presentation/Tofu/MailingListManager/lscripts"."""
          retval = ''
          remaining = messageText
          wrapped = []
          
          while len(remaining) > width:
              cut = width
              newline = string.find(remaining, '\n', 0, cut)
          
              if newline != -1:
                  cut = newline
              elif remaining[cut] != ' ':
                  temp = string.rfind(remaining, ' ', 0, cut-1)
                  if temp == -1:temp = string.find(remaining, ' ', cut-1, len(remaining))
                  if temp == -1: temp = len(remaining)
                  cut = temp
              wrapped.append(remaining[:cut])
              remaining = remaining[cut+1:]
          
          if remaining:
              wrapped.append(remaining)
          
          retval = string.join(wrapped, '\n')
          
          assert retval
          return retval

      def __split_message(self, messageText, 
                          max_consecutive_comment=12, 
                          max_consecutive_whitespace=3):
          """Split the message into main body and the footer.
          
          Email messages often contain a footer at the bottom, which
          identifies the user, and who they work for. However, GroupServer
          has lovely profiles which do this, so normally we want to snip
          the footer, to reduce clutter.
          
          In addition, many users only write a short piece of text at the
          top of the email, while the remainder of the message consists
          of all the previous posts. This method also removes the
          "bottom quoting".
          
          ARGUMENTS
              "messageText" The text to process.
              "max_consecutive_comment"    The maximum number of lines
                  of quoting to allow before snipping.
              "max_consecutive_whitespace" The maximum number of lines 
                  that just contain whitespace to allow before snipping.
          
          RETURNS
              2-tuple, containing the strings representing the main-body
              of the message, and the footer.
          
          SIDE EFFECTS
              None.

          NOTE
              Originally a stand-alone script in
              "Presentation/Tofu/MailingListManager/lscripts".
          """
          retval = ('', '')
          slines = messageText.split('\n')

          intro = []; body = []; i = 1;
          bodystart = 0; consecutive_comment = 0; 
          consecutive_whitespace = 0
          
          for line in slines:
              if (line[:2] == '--' or line[:2] == '==' or line[:2] == '__' or
                  line[:2] == '~~' or line [:3] == '- -'):
                  bodystart = 1
              
              # if we've started on the body, just append to body
              if bodystart: 
                  body.append(line)
              # count comments, but don't penalise top quoting as badly
              elif consecutive_comment >= max_consecutive_comment and i > 25: 
                  body.append(line)
                  bodystart = 1
              # if we've got less than 15 lines, just put it in the intro
              elif (i <= 15):
                  intro.append(line)
              elif (len(line) > 3 and line[:4] != '&gt;'):
                  intro.append(line)
              elif consecutive_whitespace <= max_consecutive_whitespace:
                  intro.append(line)
              else:
                  body.append(line)
                  bodystart = 1
              
              if len(line) > 3 and (line[:4] == '&gt;' or line.lower().find('wrote:') != -1):
                  consecutive_comment += 1
              else:
                  consecutive_comment = 0
              
              if len(line.strip()):
                  consecutive_whitespace = 0
              else:
                  consecutive_whitespace += 1
              
              i += 1
          
          rintro = []; trim = 1
          for line in intro[::-1]:
              if len(intro) < 5:
                  trim = 0
              if len(line) > 3:
                  ls = line[:4]
              elif line.strip():
                  ls = line.strip()[0]
              else:
                  ls = ''
              
              if trim and (ls == '&gt;' or ls == ''):
                  body.insert(0, line)
              elif trim and line.find('wrote:') > 2:
                  body.insert(0, line)
              elif trim and line.strip() and len(line.strip().split()) == 1:
                  body.insert(0, line)
              else:
                  trim = 0
                  rintro.insert(0, line)
          
          intro = '\n'.join(rintro)
          body = '\n'.join(body)
          retval = (intro.strip(), body.strip())
          
          assert retval
          assert len(retval) == 2
          return retval
      
      def __remove_file_notification(self, messageText):
          """Remove the file notification from the end of the message
          
          If an file notification was sent with the message, then
          we want to remove this from the message, as the view has
          its own way of presenting files.
          
          ARGUMENTS
              "messageText" The text to snip.
          
          RETURNS
              The message without the fine notification.
          
          ENVIRONMENT
              "self.post['xwf-notification-message-length']" The length of
                  the message, without the file-notfication.
          """
          xwf_header = 'x-xwfnotification-message-length'
          messageLength = int(getattr(self.post, xwf_header, len(messageText)))
          retval = messageText[:messageLength]
          return retval
                    
      def get_mail_body(self):
          """Get the body of the mail message, formatted for the Web.
          
          The "self.post" instance contains the plain-text version
          of the message, as was sent out to the user's via email.
          For formatting on the Web it is necessary to convert the
          text to the correct content-type, replace all URLs with
          anchor-elements, remove all at signs, wrap the message to
          80 characters, and remove the file-notification. This method
          does these things.  
          
          ARGUMENTS
              None.
          
          RETURNS
              A string representing the formatted body of the email 
              message.
          
          SIDE EFFECTS
              None.  
          """
          assert self.post
          assert self.post['mailBody']

          body = self.post['mailBody']
          
          contentType = getattr(self.post, 'content-type', None)
          ctct = Products.XWFCore.XWFUtils.convertTextUsingContentType
          text = ctct(body, contentType)  
          
          text = self.__remove_file_notification(text)
          markedUpPost = self.__markup_text(text).strip()
          retval = self.__wrap_message(markedUpPost)
          
          assert retval
          return retval

      def get_email_intro_and_remainder(self):
          """Get the intoduction and remainder text of the formatted post
          
          ARGUMENTS
              None.
              
          RETURNS
              A 2-tuple of the strings that represent the email intro
              and the remainder.
              
          SIDE EFFECTS
              None.
          """
          retval = self.__split_message(self.get_mail_body())
          return retval
      
      def get_cssClass(self):
          retval = ''
          even = (self.position % 2) == 0
          if even:
              if self.authored:
                  retval = 'emaildetails-self-even'
              else:
                  retval = 'emaildetials-even'
          else:
              if self.authored:
                  retval = 'emaildetails-self-odd'
              else:
                  retval = 'emaildetails-odd'
                  
          assert retval
          return retval

      def user_authored(self):
          """Did the user write the email message?
          
          ARGUMENTS
              None.
          
          RETURNS
              A boolean that is "True" if the current user authored the
              email message, "False" otherwise.
              
          SIDE EFFECTS
              None."""
          assert self.post
          assert self.request
          
          user = self.request.AUTHENTICATED_USER
          retval = user.getId() == self.post['mailUserId']
          
          assert retval in (True, False)
          return retval

      def author_exists(self):
          """Does the author of the post exist?
          
          RETURNS
             True if the author of the post exists on the system, False
             otherwise.
              
          SIDE EFFECTS
              None."""
      
          assert self.post
          retval = False
          
          authorId = self.post['mailUserId']
          retval = self.context.Scripts.get.user_exists(authorId)
          
          assert retval in (True, False)
          return retval
      
      def get_author_image(self):
          """Get the URL for the image of the post's author.
          
          RETURNS
             A string, representing the URL, if the author has an image,
             "None" otherwise.
             
          SIDE EFFECTS
             None.
          """
          assert self.post

          retval = None          
          if self.author_exists():
              authorId = self.post['mailUserId']
              retval = self.context.Scripts.get.user_image(authorId)
          return retval
           
      def get_author_realnames(self):
          """Get the names of the post's author.
          
          RETURNS
              The name of the post's author. 
          
          SIDE EFFECTS
             None.
          """
          assert self.post
          
          authorId = self.post['mailUserId']
          retval = self.context.Scripts.get.user_realnames(authorId)
          
          return retval
# State that the GSPostContentProvider is a Content Provider, and attach
#     to "groupserver.Post".
zope.component.provideAdapter(GSPostContentProvider, 
                              provides=zope.contentprovider.interfaces.IContentProvider,
                              name="groupserver.Post")

zope.component.provideAdapter(GSPostContentProvider, 
                              provides=zope.contentprovider.interfaces.IContentProvider,
                              name="groupserver.PostAtom")
# </zope-3 weirdness="high">