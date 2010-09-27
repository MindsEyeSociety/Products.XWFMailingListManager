from sqlalchemy.exceptions import NoSuchTableError
import sqlalchemy as sa
import datetime

import logging
log = logging.getLogger("XMLMailingListManager.queries") #@UndefinedVariable

LAST_NUM_DAYS = 60

def to_unicode(s):
    retval = s
    if not isinstance(s, unicode):
        retval = unicode(s, 'utf-8')

    return retval    

def summary(s):
    if not isinstance(s, unicode):
        s = unicode(s, 'utf-8')
    
    return s[:160]

class DigestQuery(object):
    def __init__(self, context, da):
        self.context = context
        
        self.digestTable = da.createTable('group_digest')
        self.now = datetime.datetime.now()

    def has_digest_since(self, site_id, group_id, interval=datetime.timedelta(0.9)):
        """ Have there been any digests sent in the last 'interval' time period?
        
        """
        sincetime = self.now-interval
        dt = self.digestTable
        
        statement = dt.select()

        statement.append_whereclause(dt.c.site_id==site_id)
        statement.append_whereclause(dt.c.group_id==group_id)
        statement.append_whereclause(dt.c.sent_date >= sincetime)

        r = statement.execute()
        
        result = False
        if r.rowcount:
            result = True
            
        return result

    def no_digest_but_active(self, interval='7 days', active_interval='3 months'):
        """ Returns a list of dicts containing site_id and group_id
            which have not received a digest in the 'interval' time period.
        
        """
        q = sa.text("""select DISTINCT topic.site_id,topic.group_id from 
               (select site_id, group_id, max(sent_date) as sent_date from
                group_digest group by site_id,group_id) as latest_digest,topic
                where (topic.site_id=latest_digest.site_id and
                       topic.group_id=latest_digest.group_id and
                latest_digest.sent_date < CURRENT_TIMESTAMP-interval '%(interval)s'
                and topic.last_post_date >
                CURRENT_TIMESTAMP-interval '%(active_interval)s');""" % locals(), 
                   engine=self.digestTable.engine)

        r = q.execute()
        
        retval = []
        if r.rowcount:
            retval = [ {'site_id': x['site_id'],
                        'group_id': x['group_id']} for x in r ]
        return retval
    
    def update_group_digest(self, site_id, group_id):
        """ Update the group_digest table when we send out a new digest.
        
        """
        dt = self.digestTable
        
        statement = dt.insert()

        statement.execute(site_id=site_id,group_id=group_id,sent_date=self.now)

class MemberQuery(object):
    # how many user ID's should we attempt to pass to the database before
    # we just do the filtering ourselves to avoid the overhead on the database
    USER_FILTER_LIMIT = 200

    def __init__(self, context, da):
        self.context = context
        
        self.emailSettingTable = da.createTable('email_setting')
        self.userEmailTable = da.createTable('user_email')
        self.groupUserEmailTable = da.createTable('group_user_email')
        self.emailBlacklist = da.createTable('email_blacklist')

    def process_blacklist(self, email_addresses):
        eb = self.emailBlacklist

        blacklist = eb.select()
        r = blacklist.execute()
        blacklisted_addresses = []
        if r.rowcount:
            for row in r:
                blacklist_email = row['email'].strip()
                if blacklist_email:
                    blacklisted_addresses.append(blacklist_email)
                    
        for blacklist_email in blacklisted_addresses:
            if blacklist_email in email_addresses:
                email_addresses.remove(blacklist_email)
                log.warn('Found blacklisted email address: "%s" in email list' % blacklist_email)

        return email_addresses

    def get_member_addresses(self, site_id, group_id, id_getter, preferred_only=True, process_settings=True, verified_only=True):
        # TODO: We currently can't use site_id
        # TODO: Should only get verified addresses
        site_id = ''

        user_ids = id_getter(ids_only=True)
        est = self.emailSettingTable        
        uet = self.userEmailTable
        guet = self.groupUserEmailTable
        
        ignore_ids = []
        email_addresses = []

        # process anything that might include/exclude specific email addresses
        # or block email delivery
        if process_settings:
            email_settings = est.select()
            email_settings.append_whereclause(est.c.site_id==site_id)
            email_settings.append_whereclause(est.c.group_id==group_id)
            
            r = email_settings.execute()
        
            if r.rowcount:
                for row in r:
                    ignore_ids.append(row['user_id'])
        
            cols = [guet.c.user_id, guet.c.email]
            email_group = sa.select(cols)
            
            email_group.append_whereclause(guet.c.site_id==site_id)
            email_group.append_whereclause(guet.c.group_id==group_id)
            if verified_only:
                email_group.append_whereclause(guet.c.email==uet.c.email)
                email_group.append_whereclause(uet.c.verified_date != None)
         
            r = email_group.execute()
            if r.rowcount:
                n_ignore_ids = []
                for row in r:
                    # double check for security that this user should actually
                    # be receiving email for this group
                    if row['user_id'] in user_ids and row['user_id'] not in ignore_ids:
                        n_ignore_ids.append(row['user_id'])
                        email_addresses.append(row['email'].lower())

                ignore_ids += n_ignore_ids

            # remove any ids we have already processed
            user_ids = filter(lambda x: x not in ignore_ids, user_ids)

        email_user = uet.select()
        if preferred_only:
            email_user.append_whereclause(uet.c.is_preferred==True)
        if verified_only:
            email_user.append_whereclause(uet.c.verified_date != None)
                    
        if len(user_ids) <= self.USER_FILTER_LIMIT:
            email_user.append_whereclause(uet.c.user_id.in_(*user_ids))

        r = email_user.execute()
        if r.rowcount:
            for row in r:
                if len(user_ids) > self.USER_FILTER_LIMIT:
                    if row['user_id'] in user_ids:
                        email_addresses.append(row['email'].lower())                        
                else:
                    email_addresses.append(row['email'].lower())

        email_addresses = self.process_blacklist(email_addresses)

        return email_addresses

    def get_digest_addresses(self, site_id, group_id, id_getter):
        # TODO: We currently can't use site_id
        # TODO: Should only get verified addresses
        site_id = ''
        
        user_ids = id_getter(ids_only=True)
        est = self.emailSettingTable        
        uet = self.userEmailTable
        guet = self.groupUserEmailTable

        email_settings = est.select()
        email_settings.append_whereclause(est.c.site_id==site_id)
        email_settings.append_whereclause(est.c.group_id==group_id)
        email_settings.append_whereclause(est.c.setting=='digest')
        
        r = email_settings.execute()
        
        digest_ids = []
        ignore_ids = []
        email_addresses = []
        if r.rowcount:
            for row in r:
                if row['user_id'] in user_ids:
                    digest_ids.append(row['user_id'])
        
        email_group = guet.select()
        email_group.append_whereclause(guet.c.site_id==site_id)
        email_group.append_whereclause(guet.c.group_id==group_id)
        email_group.append_whereclause(guet.c.user_id.in_(*digest_ids))
        
        r = email_group.execute()
        if r.rowcount:
            for row in r:
                ignore_ids.append(row['user_id'])
                email_addresses.append(row['email'].lower())
        
        # remove any ids we have already processed
        digest_ids = filter(lambda x: x not in ignore_ids, digest_ids)

        email_user = uet.select()
        email_user.append_whereclause(uet.c.is_preferred==True)      
        email_user.append_whereclause(uet.c.user_id.in_(*digest_ids))
        
        r = email_user.execute()        
        if r.rowcount:
            for row in r:
                if row['user_id'] in user_ids:
                    email_addresses.append(row['email'].lower())

        email_addresses = self.process_blacklist(email_addresses)

        return email_addresses
        
class MessageQuery(object):
    def __init__(self, context, da):
        self.context = context
        
        self.topicTable = da.createTable('topic')
        self.topic_word_countTable = da.createTable('topic_word_count')
        self.postTable = da.createTable('post')
        self.fileTable = da.createTable('file')
        
        try:
            self.post_id_mapTable = da.createTable('post_id_map')
        except NoSuchTableError:
            self.post_id_mapTable = None

    def __add_std_where_clauses(self, statement, table, 
                                       site_id, group_ids=[]):
        '''Add the standard "where" clauses to an SQL statement
        
        DESCRIPTION
            It is very common to only search a table for an
            object from a particular set of groups, on a particular site.
            This method add the appropriate where-clauses to do this.
        
        ARGUMENTS
            "statement":  An SQL statement.
            "site_id":    The IS for the site that is being searched.
            "group_ids":  A list of IDs of the groups that are being 
                          searched.
        RETURNS
            The SQL statement, with the site-restrection and group
            restrictions appended to the "WHERE" clause.
            
        SIDE EFFECTS
        '''
        statement.append_whereclause(table.c.site_id==site_id)
        if group_ids:
            inStatement = table.c.group_id.in_(*group_ids)
            statement.append_whereclause(inStatement)

        return statement

    def post_id_from_legacy_id(self, legacy_post_id):
        """ Given a legacy (pre-1.0) GS post_id, determine what the new
        post ID is, if we know.
        
        This is primarily used for backwards compatibility in the redirection
        system.
        
        """
        pit = self.post_id_mapTable
        if not pit:
            return None
        
        statement = pit.select()
        
        statement.append_whereclause(pit.c.old_post_id==legacy_post_id)
        
        r = statement.execute()
        
        post_id = None
        if r.rowcount:
            result = r.fetchone()
            post_id = result['new_post_id']
            
        return post_id
        
    def topic_id_from_post_id(self, post_id):
        """ Given a post_id, determine which topic it came from.
        
        """
        pt = self.postTable
        statement = pt.select()
        statement.append_whereclause(pt.c.post_id==post_id)
        r = statement.execute()
        
        topic_id = None
        if r.rowcount:
            result = r.fetchone()
            topic_id = result['topic_id']
        
        return topic_id

    def latest_posts(self, site_id, group_ids=[], limit=None, offset=0):
        statement = self.postTable.select()
        self.__add_std_where_clauses(statement, self.postTable, 
                                     site_id, group_ids)
        statement.limit = limit
        statement.offset = offset
        statement.order_by(sa.desc(self.postTable.c.date))

        r = statement.execute()
        
        retval = []
        if r.rowcount:
            retval = [ {'post_id': x['post_id'], 
                        'topic_id': x['topic_id'], 
                        'subject': to_unicode(x['subject']), 
                        'date': x['date'], 
                        'author_id': x['user_id'], 
                        'body': to_unicode(x['body']),
                        'summary': summary(x['body']), 
                        'files_metadata': x['has_attachments'] 
                                  and self.files_metadata(x['post_id']) or [],
                        'has_attachments': x['has_attachments']} for x in r ]
            
        return retval
    
    def post_count(self, site_id, group_ids=[]):
        statement = sa.select([sa.func.sum(self.topicTable.c.num_posts)]) #@UndefinedVariable
        self.__add_std_where_clauses(statement, self.topicTable, 
                                           site_id, group_ids)
        r = statement.execute()

        retval = r.scalar()
        if retval == None:
            retval = 0
        assert retval >= 0
        return retval
            
    def topic_count(self, site_id, group_ids=[]):
        statement = sa.select([sa.func.count(self.topicTable.c.topic_id)])
        self.__add_std_where_clauses(statement, self.topicTable, 
                                     site_id, group_ids)
        r = statement.execute()

        retval = r.scalar()
        assert retval >= 0
        return retval

    def latest_topics(self, site_id, group_ids=[], limit=None, offset=0):
        """
            Returns: 
             ({'topic_id': ID, 'subject': String, 'first_post_id': ID,
               'last_post_id': ID, 'count': Int, 'last_post_date': Date,
               'group_id': ID, 'site_id': ID}, ...)

        """
        tt = self.topicTable
        
        statement = tt.select()
        self.__add_std_where_clauses(statement, self.topicTable, 
                                     site_id, group_ids)
                
        statement.limit = limit
        statement.offset = offset
        statement.order_by(sa.desc(tt.c.last_post_date))
        
        r = statement.execute()

        retval = []        
        if r.rowcount:
            retval = [ {'topic_id': x['topic_id'], 
                        'site_id': x['site_id'], 
                        'group_id': x['group_id'], 
                        'subject': to_unicode(x['original_subject']),
                        'first_post_id': x['first_post_id'], 
                        'last_post_id': x['last_post_id'], 
                        'count': x['num_posts'], 
                        'last_post_date': x['last_post_date']} for x in r ]
                        
        return retval

    def _nav_post(self, curr_post_id, direction, topic_id=None):
        op = direction == 'prev' and '<=' or '>='
        dir = direction == 'prev' and 'desc' or 'asc'
        
        topic_id_filter = ''
        if topic_id:
            topic_id_filter = 'post.topic_id=curr_post.topic_id and'
        
        q = sa.text("""select post.date, post.post_id, post.topic_id,
                       post.subject, post.user_id, post.has_attachments
                    from post, 
                   (select date,group_id,site_id,post_id,topic_id from post where 
                    post_id='%(curr_post_id)s') as curr_post where
                   post.group_id=curr_post.group_id and
                   post.site_id=curr_post.site_id and
                   post.date %(op)s curr_post.date and
                   %(topic_id_filter)s
                   post.post_id != curr_post.post_id
                   order by post.date %(dir)s limit 1""" % locals(), 
                   engine=self.postTable.engine)
        
        r = q.execute().fetchone()
        if r:
            return {'post_id': r['post_id'], 
                    'topic_id': r['topic_id'], 
                    'subject': to_unicode(r['subject']), 
                    'date': r['date'], 
                    'author_id': r['user_id'], 
                    'has_attachments': r['has_attachments']}
        return None

    def previous_post(self, curr_post_id):
        """ Find the post prior to the given post ID.

            Returns:
               {'post_id': ID, 'topic_id': ID, 'subject': String,
                'date': Date, 'author_id': String, 'has_attachments': Bool}
             or
                None

        """
        return self._nav_post(curr_post_id, 'prev')


    def next_post(self, curr_post_id):
        """ Find the post after the given post ID.

            Returns:
               {'post_id': ID, 'topic_id': ID, 'subject': String,
                'date': Date, 'author_id': String, 'has_attachments': Bool}
             or
                None
        
        """
        return self._nav_post(curr_post_id, 'next')

    def _nav_topic(self, curr_topic_id, direction):
        op = direction == 'prev' and '<=' or '>='
        dir = direction == 'prev' and 'desc' or 'asc'
        
        q = sa.text("""select topic.last_post_date as date,
                              topic.topic_id, topic.last_post_id,
                              topic.original_subject as subject
                    from topic, 
                   (select topic_id,last_post_date as date,group_id,site_id
                    from topic where 
                    topic_id='%s') as curr_topic where
                   topic.group_id=curr_topic.group_id and
                   topic.site_id=curr_topic.site_id and
                   topic.last_post_date %s curr_topic.date and
                   topic.topic_id != curr_topic.topic_id
                   order by date %s limit 1""" % 
                   (curr_topic_id, op, dir), 
                   engine=self.postTable.engine)
        
        r = q.execute().fetchone()
        if r:
            return {'topic_id': r['topic_id'], 
                    'last_post_id': r['last_post_id'], 
                    'subject': to_unicode(r['subject']), 
                    'date': r['date']}
        return None

    def later_topic(self, curr_topic_id):
        """ Find the topic prior to the given topic ID.

            Returns:
               {'last_post_id': ID, 'topic_id': ID,
                'subject': String, 'date': Date}
             or
                None

        """
        return self._nav_topic(curr_topic_id, 'prev')

    def earlier_topic(self, curr_topic_id):
        """ Find the topic after the given topic ID.

            Returns:
               {'last_post_id': ID, 'topic_id': ID,
                'subject': String, 'date': Date}
             or
                None
        
        """
        return self._nav_topic(curr_topic_id, 'next')
    
    def topic_post_navigation(self, curr_post_id):
        """ Retrieve first/last, next/prev navigation relative to a post, within a topic.
            Used for navigation of single posts *within* a topic, not for general post
            navigation.

            Returns:
                {'first_post_id': ID, 'last_post_id': ID,
                 'previous_post_id': ID, 'next_post_id': ID}
            
            ID may be None.
             
        """
        first_post_id = None
        last_post_id = None
        next_post_id = None
        previous_post_id = None
        
        tt = self.topicTable
        
        topic_id = self.topic_id_from_post_id(curr_post_id)

        if topic_id:
            statement = tt.select()
        
            statement.append_whereclause(tt.c.topic_id==topic_id)
        
            r = statement.execute()
        
            if r.rowcount:
                result = r.fetchone()
            
                first_post_id = result['first_post_id']
                last_post_id = result['last_post_id']
        
            r = self._nav_post(curr_post_id, 'next', topic_id)
            if r:
                assert r['topic_id'] == topic_id, "Topic ID should always match"
                next_post_id = r['post_id']
            
            r = self._nav_post(curr_post_id, 'prev', topic_id)
            if r:
                assert r['topic_id'] == topic_id, "Topic ID should always match"
                previous_post_id = r['post_id']
        
        return {'first_post_id': first_post_id, 'last_post_id': last_post_id, 
                'previous_post_id': previous_post_id, 'next_post_id': next_post_id}
        
    def topic_posts(self, topic_id):
        """ Retrieve all the posts in a topic.
            
            Returns:
                ({'post_id': ID, 'subject': String,
                  'date': Date, 'author_id': ID,
                  'files_metadata': [Metadata],
                  'body': Text}, ...)
             or
                []

        """
        pt = self.postTable
        statement = pt.select()
        statement.append_whereclause(pt.c.topic_id==topic_id)
        statement.order_by(sa.asc(pt.c.date))
        
        r = statement.execute()
        retval = []
        if r.rowcount:
            retval = [ {'post_id': x['post_id'], 
                        'subject': to_unicode(x['subject']), 
                        'date': x['date'], 
                        'author_id': x['user_id'],
                        'files_metadata': x['has_attachments'] 
                                  and self.files_metadata(x['post_id']) or [],
                        'body': to_unicode(x['body']),
                        'summary': summary(x['body'])} for x in r ]
        return retval

    
    def post(self, post_id):
        """ Retrieve a particular post.
            
            Returns:
                {'post_id': ID, 'group_id': ID, 'site_id': ID,
                 'subject': String,
                 'date': Date, 'author_id': ID,
                 'body': Text,
                 'files_metadata': [Metadata]
                 }
             or
                None

        """
        pt = self.postTable
        statement = pt.select()
        statement.append_whereclause(pt.c.post_id==post_id)
        
        r = statement.execute()
        if r.rowcount:
            assert r.rowcount == 1, "Posts should always be unique"
            row = r.fetchone()
            
            return {'post_id': row['post_id'],
                    'group_id': row['group_id'],
                    'site_id': row['site_id'],
                    'subject': to_unicode(row['subject']),
                    'date': row['date'],
                    'author_id': row['user_id'],
                    'files_metadata': row['has_attachments'] and 
                                      self.files_metadata(row['post_id']) or [],
                    'body': to_unicode(row['body']),
                    'summary': summary(row['body'])}
        
        return None

    def topic(self, topic_id):
        """
            Returns: 
             {'topic_id': ID, 'subject': String, 'first_post_id': ID,
               'last_post_id': ID, 'count': Int, 'last_post_date': Date,
               'group_id': ID, 'site_id': ID}
        """
        tt = self.topicTable
        statement = tt.select()
        statement.append_whereclause(tt.c.topic_id==topic_id)

        retval = None
        r = statement.execute()
        if r.rowcount:
            assert r.rowcount == 1, "Topics should always be unique"
            row = r.fetchone()
            retval = {'topic_id': row['topic_id'], 
                      'site_id': row['site_id'],
                      'group_id': row['group_id'],
                      'subject': to_unicode(row['original_subject']), 
                      'first_post_id': row['first_post_id'],
                      'last_post_id': row['last_post_id'],
                      'last_post_date': row['last_post_date'],
                      'count': row['num_posts']}
        return retval

    def files_metadata(self, post_id):
        """ Retrieve the metadata of all files associated with this post.
            
            Returns:
                {'file_id': ID, 'mime_type': String,
                 'file_name': String, 'file_size': Int}
             or
                []

        """
        ft = self.fileTable
        statement = ft.select()
        statement.append_whereclause(ft.c.post_id==post_id)
        
        r = statement.execute()
        out = []
        if r.rowcount:
            out = []
            for row in r:
                out.append({'file_id': row['file_id'],
                            'file_name': to_unicode(row['file_name']),
                            'date': row['date'],
                            'mime_type': to_unicode(row['mime_type']),
                            'file_size': row['file_size']})
                
        return out

    def active_groups(self, interval='1 day'):
        """Retrieve all active groups
        
        An active group is one which has had a post added to it within
        "interval".
        
        ARGUMENTS
            "interval"  An SQL interval, as a string, made up of 
                        "quantity unit". The quantity is an integer value,
                        while the unit is one of "second", "minute", "hour", 
                        "day", "week", "month", "year", "decade", 
                        "century", or "millennium".
                        
        RETURNS
            A list of dictionaries, which contain "group_id" and "site_id".
            
        SIDE EFFECTS
            None.
        
        See Also
            Section 8.5.1.4 of the PostgreSQL manual:
            http://www.postgresql.org/docs/8.0/interactive/datatype-datetime.html
        """
        tt = self.topicTable
        statement = sa.text("""SELECT DISTINCT group_id, site_id
                               FROM topic 
                               WHERE age(CURRENT_TIMESTAMP, last_post_date) < INTERVAL '%s';""" % interval,
                            engine=tt.engine)
        r = statement.execute()
        retval = []
        if r.rowcount:
            retval = [ {'site_id': x['site_id'], 
                        'group_id': x['group_id']} for x in r ]
        return retval        
  
    def topic_search(self, search_string, site_id, group_ids=()):
        """ Retrieve all the topics matching a particular search string.
        
            Returns:
             ({'topic_id': ID, 'subject': String, 'first_post_id': ID,
               'last_post_id': ID, 'count': Int, 'last_post_date': Date,
               'group_id': ID, 'site_id': ID}, ...)
               
        """
        tt = self.topicTable
        twc = self.topic_word_countTable
        t = tt.join(twc, twc.c.topic_id==tt.c.topic_id)
        statement = sa.select((tt.c.topic_id,tt.c.site_id,tt.c.group_id,
                               tt.c.original_subject, tt.c.first_post_id,
                               tt.c.last_post_id, tt.c.num_posts,
                               tt.c.last_post_date), from_obj=[t])
        self.__add_std_where_clauses(statement, tt, 
                                     site_id, group_ids)
        
        statement.append_whereclause(twc.c.word.in_(*search_string.split()))
        statement.order_by(sa.desc(tt.c.last_post_date))
        statement.limit = 30
        
        r = statement.execute()

        retval = []
        if r.rowcount:
            retval = [ {'topic_id': x['topic_id'], 
                        'site_id': x['site_id'], 
                        'group_id': x['group_id'], 
                        'subject': to_unicode(x['original_subject']),
                        'first_post_id': x['first_post_id'], 
                        'last_post_id': x['last_post_id'], 
                        'count': x['num_posts'], 
                        'last_post_date': x['last_post_date']} for x in r ]
        return retval

    def num_posts_after_date(self, site_id, group_id, user_id, date):
        assert type(site_id)  == str
        assert type(group_id) == str
        assert type(user_id)  == str
                
        pt = self.postTable
        cols = [sa.func.count(pt.c.post_id)]
        statement = sa.select(cols)
        statement.append_whereclause(pt.c.site_id  == site_id)
        statement.append_whereclause(pt.c.group_id == group_id)
        statement.append_whereclause(pt.c.user_id  == user_id)
        statement.append_whereclause(pt.c.date  > date)
        
        r = statement.execute()
        retval = r.scalar()
        assert type(retval) == long, 'retval is %s' % type(retval)
        return retval
        
class BounceQuery(object):
    
    def __init__(self, context, da):
        self.bounceTable = da.createTable('bounce')

    def addBounce(self, groupId, siteId, userId, email):
        bt = self.bounceTable
        i = bt.insert()
        now = datetime.datetime.now()
        i.execute(date=now, user_id=userId, group_id=groupId, 
                  site_id=siteId, email=email)
        
    def previousBounces(self, email):
        """ Checks for the number of bounces from this email address
            in the past LAST_NUM_DAYS. 
        """
        bt = self.bounceTable
        now = datetime.datetime.now()
        s = bt.select()
        s.append_whereclause(bt.c.email==email)
        s.append_whereclause(bt.c.date > (now-datetime.timedelta(LAST_NUM_DAYS)))
        s.order_by(sa.desc(bt.c.date))
        
        r = s.execute()
        bounces = []
        if r.rowcount:
            for row in r:
                bounceDate = row['date'].strftime("%Y%m%d")
                if bounceDate not in bounces:
                    bounces.append(bounceDate)
        return bounces

