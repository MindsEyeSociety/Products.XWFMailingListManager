from Products.Five import BrowserView
from zope.component import createObject
import Products.GSContent
from Products.GSSearch import queries
from view import GSPostingInfo # FIX

class GSTopicsView(BrowserView, GSPostingInfo):
      """List of latest topics in the group."""
      def __init__(self, context, request):
          self.context = context
          self.request = request

          self.__author_cache = {}

          self.siteInfo = createObject('groupserver.SiteInfo', 
            context)
          self.groupInfo = createObject('groupserver.GroupInfo', context)

          da = context.zsqlalchemy 
          assert da
          self.messageQuery = queries.MessageQuery(context, da)
  
          self.start = int(self.request.form.get('start', 0))
          self.end = int(self.request.form.get('end', 20))
          # Swap the start and end, if necessary
          if self.start > self.end:
              tmp = self.end
              self.end = self.start
              self.start = tmp

          messages = self.context.messages
          lists = messages.getProperty('xwf_mailing_list_ids')

          limit = self.get_summary_length()

          self.numTopics = self.messageQuery.topic_count(self.siteInfo.get_id(), lists)
          if self.start > self.numTopics:
              self.start = self.numTopics - limit

          searchTokens = createObject('groupserver.SearchTextTokens', '')
          self.topics = self.messageQuery.topic_search_keyword(
            searchTokens, self.siteInfo.get_id(), 
            [self.groupInfo.get_id()], limit=limit, offset=self.start)

          tIds = [t['topic_id'] for t in self.topics]
          self.topicFiles = self.messageQuery.files_metadata_topic(tIds)

      def get_later_url(self):
          newStart = self.start - self.get_summary_length()
          if newStart < 0:
              newStart = 0
          newEnd = newStart + self.get_summary_length()
          
          if newStart != self.start and newStart:
              retval = 'topics.html?start=%d&end=%d' % (newStart, newEnd)
          elif newStart != self.start and not newStart:
              retval = 'topics.html'
          else:
              retval = ''
          return retval
      
      def get_earlier_url(self):
          newStart = self.end
          newEnd = newStart + self.get_summary_length()
          if newStart < self.numTopics:
              retval = 'topics.html?start=%d&end=%d' % (newStart, newEnd)
          else:
              retval = ''
          return retval
      
      def get_last_url(self):
          newStart = self.numTopics - self.get_summary_length()
          newEnd = self.numTopics
          return 'topics.html?start=%d&end=%d' % (newStart, newEnd)

      def get_summary_length(self):
          assert hasattr(self, 'start')
          assert hasattr(self, 'end')
          assert self.start <= self.end
          
          retval = self.end - self.start
          
          assert retval >= 0
          return retval;
          
      def get_topics(self):
          assert hasattr(self, 'topics')
          return self.topics

          
      def get_sticky_topics(self):
          assert hasattr(self, 'messageQuery'), 'No message query'
          assert hasattr(self, 'groupInfo'), 'No group info'
          if not hasattr(self, 'stickyTopics'):
              stickyTopicsIds = self.groupInfo.get_property('sticky_topics', [])
              topics = filter(lambda t: t!=None, [self.messageQuery.topic(topicId) 
                                                  for topicId in stickyTopicsIds])
              self.stickyTopics = topics
              
          retval =  self.stickyTopics
          assert hasattr(self, 'stickyTopics'), 'Sticky topics not cached'
          return retval

      def get_non_sticky_topics(self):
          stickyTopics = self.get_sticky_topics()
          stickyTopicIds = map(lambda t: t['topic_id'], stickyTopics)
          allTopics = self.get_topics()

          r = lambda r: r.replace('/','-').replace('.','-')
          retval = []
          for topic in self.topics:
              t = topic
              authorInfo = self.__author_cache.get(t['last_post_user_id'], None)
              if not authorInfo:
                  authorInfo = createObject('groupserver.AuthorInfo', 
                    self.context, t['last_post_user_id'])
                  self.__author_cache[t['last_post_user_id']] = authorInfo
              authorId = authorInfo.get_id()
              authorD = {
                'exists': authorInfo.exists(),
                'id': authorId,
                'name': authorInfo.get_realnames(),
                'url': authorInfo.get_url(),
              }
              t['last_author'] = authorD

              files = [{'name': f['file_name'],
                        'url': '/r/topic/%s#post-%s' % (f['post_id'], f['post_id']),
                        'icon': r(f['mime_type']),
                       } for f in self.topicFiles 
                       if f['topic_id'] == t['topic_id']]
                       
              t['files'] = files
              if t['topic_id'] not in stickyTopicIds:
                  retval.append(t)
          return retval

      def process_form(self, *args):
          pass
