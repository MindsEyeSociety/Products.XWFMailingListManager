import sys, re, datetime, time, types, string
import Products.Five, Products.GSContent, DateTime, Globals
#import Products.Five.browser.pagetemplatefile
import zope.schema
import zope.app.pagetemplate.viewpagetemplatefile
import zope.pagetemplate.pagetemplatefile
import zope.interface, zope.component, zope.publisher.interfaces
import zope.viewlet.interfaces, zope.contentprovider.interfaces 

from view import GSGroupInfo

import DocumentTemplate, Products.XWFMailingListManager

import Products.GSContent, Products.XWFCore.XWFUtils
import queries

class GSLatestPostsView(Products.Five.BrowserView):
      def __init__(self, context, request):
          self.siteInfo = Products.GSContent.view.GSSiteInfo( context )
          self.groupInfo = GSGroupInfo( context )
           
          self.context = context
          self.request = request
          
          self.start = int(self.request.form.get('start', 0))
          self.end = int(self.request.form.get('end', 20))
          # Swap the start and end, if necessary
          if self.start > self.end:
              tmp = self.end
              self.end = self.start
              self.start = tmp
              
          da = context.zsqlalchemy 
          assert da
          self.messageQuery = queries.MessageQuery(context, da)
          
          messages = self.context.messages
          lists = messages.getProperty('xwf_mailing_list_ids')
                   
          if self.siteInfo.get_id() == 'example_division':
              limit = self.get_chunk_length()
              self.numPosts = self.messageQuery.post_count('ogs', lists)
              self.posts = self.messageQuery.latest_posts('ogs',
                                                          lists, limit=limit,
                                                          offset=self.start)
          else:
              self.numPosts = self.messageQuery.post_count(self.siteInfo.get_id(),
                                                          lists)
              self.posts = self.messageQuery.latest_posts(self.siteInfo.get_id(), 
                                                          lists, limit=limit,
                                                          offset=self.start)

      def get_posts(self):
          assert self.posts
          return self.posts

      def get_chunk_length(self):
          assert hasattr(self, 'start')
          assert hasattr(self, 'end')
          assert self.start <= self.end
          
          retval = self.end - self.start
          
          assert retval >= 0
          return retval;
          
      def get_previous_chunk_url(self):
          assert hasattr(self, 'start')

          newStart = self.start - self.get_chunk_length()
          if newStart < 0:
              newStart = 0
          newEnd = newStart + self.get_chunk_length()
          
          if newStart != self.start and newStart:
              retval = 'posts.html?start=%d&end=%d' % (newStart, newEnd)
          elif newStart != self.start and not newStart:
              retval = 'posts.html'
          else:
              retval = ''
          return retval

      def get_next_chunk_url(self):
          assert hasattr(self, 'end')

          newStart = self.end
          newEnd = newStart + self.get_chunk_length()
          if newStart < self.numPosts:
              retval = 'posts.html?start=%d&end=%d' % (newStart, newEnd)
          else:
              retval = ''
          return retval

      def get_last_chunk_url(self):
          newStart = self.numPosts - self.get_chunk_length()
          newEnd = self.numPosts
          return 'posts.html?start=%d&end=%d' % (newStart, newEnd)

      def process_form(self):
          pass
