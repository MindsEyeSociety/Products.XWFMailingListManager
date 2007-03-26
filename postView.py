'''GroupServer-Content View of a Single Post
'''
from zope.app.traversing.interfaces import TraversalError
from interfaces import IGSPostView
from zope.interface import implements
from Products.Five.traversable import Traversable
from zope.app.traversing.interfaces import ITraversable
import Products.GSContent, Products.XWFCore.XWFUtils
import Products.XWFMailingListManager.stickyTopicToggleContentProvider
import queries
import view

class GSPostView(Traversable):
      """A view of a single post.
      
      A view of a single post shares much in common with a view of an 
      entire topic, which is why it inherits from "GSTopicView". The main
      semantic difference is the ID specifies post to display, rather than
      the first post in the topic.   
      """
      implements(IGSPostView, ITraversable)
      def __init__(self, context, request):
          self.context = context
          self.request = request

          self.siteInfo = Products.GSContent.view.GSSiteInfo( context )
          self.groupInfo = view.GSGroupInfo( context )
          
          self.archive = context.messages
          
          self.postId = None
          
      def traverse(self, name, furtherPath):
          #
          # TODO: this would probably be a good spot to check if the
          # postId is valid, and if not redirect to a helpful message
          #
          if not self.postId:
              self.postId = name
              self.update()
          else:
              raise TraversalError, "Post ID was already specified"
          
          return self
      
      def update(self):
          da = self.context.zsqlalchemy 
          assert da, 'No data-adaptor found'
          
          self.messageQuery = queries.MessageQuery(self.context, da)
          self.post = self.messageQuery.post(self.postId)
          self.relatedPosts = self.messageQuery.topic_post_navigation(self.postId)
          
      def get_topic_title(self):
          assert hasattr(self, 'post')
          assert self.post.has_key('subject')
          return self.post['subject']
          
      def get_previous_post(self):
          assert hasattr(self, 'relatedPosts')
          assert self.relatedPosts.has_key('previous_post_id')
          return self.relatedPosts['previous_post_id']
                    
      def get_next_post(self):
          assert hasattr(self, 'relatedPosts')
          assert self.relatedPosts.has_key('next_post_id')
          return self.relatedPosts['next_post_id']
          
      def get_first_post(self):
          assert hasattr(self, 'relatedPosts')
          assert self.relatedPosts.has_key('first_post_id')
          return self.relatedPosts['first_post_id']
          
      def get_last_post(self):
          assert hasattr(self, 'relatedPosts')
          assert self.relatedPosts.has_key('last_post_id')
          return self.relatedPosts['last_post_id']
          
      def get_post(self):
          assert hasattr(self, 'post')
          return self.post
          