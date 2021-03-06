#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
reload(sys)
sys.setdefaultencoding('utf8')

from HTMLParser import HTMLParser
import urllib, json
import httplib
from urlparse import urlparse

import common, db

def Start(db_, artist_list):

    GetSongs_URL_Template_ = 'http://music.baidu.com/data/user/getsongs?start=%s&ting_uid=%s&order=hot'
    SongLink_URL_Template_ = 'http://play.baidu.com/data/music/songlink?songIds=%s'
    PRE_URL_ = 'http://play.baidu.com'

    Find_Song_Switch_ = [False]
    Artist_Id_ = ''
    Order_ = [0]
    SongNameMap = {}

    h = '127.0.0.1:8098'
    if '-h' in sys.argv:
        h_index = sys.argv.index('-h')
        if h_index and h_index > 0 and len(sys.argv) > h_index + 1:
            h = sys.argv[h_index + 1]
    
    order = int(common.get_argv('-order', 25))

    RIAK_HOSTNAME = h
    RIAK_URL_TEMPLATE = '/buckets/music/keys/%s'
    RIAK_LRC_URL_TEMPLATE = '/buckets/lrc/keys/%s'

    dwnn = int(common.get_argv('-dwnn', 25))

    ELS_HOSTNAME = str(common.get_argv('-esh', 'localhost:9200'))
    ELS_URL_TEMPLATE = '/local/music/%s'

    dwn_music = [common.Downloader(RIAK_HOSTNAME, RIAK_URL_TEMPLATE, dwnn)]
    dwn_lrc = [common.Downloader(RIAK_HOSTNAME, RIAK_LRC_URL_TEMPLATE, dwnn)]
    elsup = [common.ElsUploader(ELS_HOSTNAME, ELS_URL_TEMPLATE, dwnn)]

    def elsup_destruct(this_):
        elsup[0].close()
        elsup[0] = common.ElsUploader(ELS_HOSTNAME, ELS_URL_TEMPLATE, dwnn)
        elsup[0].evtExpire = elsup_destruct

    elsup[0].evtExpire = elsup_destruct

    def dwn_music_destruct(this_):
        dwn_music[0].close()
        dwn_music[0] = common.Downloader(RIAK_HOSTNAME, RIAK_URL_TEMPLATE, dwnn)
        dwn_music[0].evtExpire = dwn_music_destruct

    dwn_music[0].evtExpire = dwn_music_destruct
    
    def dwn_lrc_destruct(this_):
        dwn_lrc[0].close()
        dwn_lrc[0] = common.Downloader(RIAK_HOSTNAME, RIAK_LRC_URL_TEMPLATE, dwnn)
        dwn_lrc[0].evtExpire = dwn_lrc_destruct

    dwn_lrc[0].evtExpire = dwn_lrc_destruct

    def Find_Song_Link(tag, attrs):
        try:
            if tag == 'a':
                for k, v in attrs:
                    if(k and k == 'href' and v and v.find('/song/') != -1):
                        href_ = v[v.find('/song/') + len('/song/'):]
                        if href_.find('/') != -1:
                            href_ = href_[:href_.find('/')]
                        #Song_List_.add(href_)
                        raw_content = common.http_read(SongLink_URL_Template_ % href_)
                        if raw_content is None:
                            continue
                        raw_object = json.loads(raw_content)
                        songList = raw_object['data']['songList']
                        if len(songList) > 0:
                            song_ = songList[0]
                            songId = song_['songId']
                            songName = song_['songName']
                            lrclink = PRE_URL_ + song_['lrcLink']
                            songlink = song_['songLink']
                            rate = song_['rate']
                            size = song_['size']
                            artist_id = Artist_Id_
                            if songName not in SongNameMap:
                                SongNameMap[songName] = None
                                if(order > Order_[0] and songlink and songlink != ''):#important
                                    db_.add_song(songId, songName, lrclink, songlink, rate, size, artist_id, Order_[0])
                                    obj = {
                                        "songId": songId,
                                        "songName": songName,
                                        "rate": rate,
                                        "size": size,
                                        "order": Order_[0],
                                        "artistId": artist_id}
                                    elsup[0].transfer(json.dumps(obj), songId)
                                    #elsup[0].transfer('{'\
                                    #    '"songId": %d,'\
                                    #    '"songName": "%s",'\
                                    #    '"rate": %d,'\
                                    #    '"size": %d,'\
                                    #    '"order": %d,'\
                                    #    '"artistId": "%s"}' % (songId, songName, rate, size, Order_[0], artist_id), songId)
                                    for i in range(0, 3):
                                        if i > 0:
                                            common.log('try download music %s again, time: %d' % (songId, i))
                                        if dwn_music[0].transfer(songlink, songId, 'audio/mpeg'):
                                            break
                                        elif i == 2:
                                            db_.add_failed(songlink, songId, 'audio/mpeg', 1)
                                    if lrclink.endswith('.lrc'):
                                        for i in range(0, 3):
                                            if i > 0:
                                                common.log('try download lrc %s again, time: %d' % (songId, i))
                                            if dwn_lrc[0].transfer(lrclink, songId, 'text/plain'):
                                                break
                                            elif i == 2:
                                                db_.add_failed(lrclink, songId, 'text/plain', 2)
                                    Order_[0] = Order_[0] + 1
                            #Order_[0] = Order_[0] + 1
                            print 'song %d has been saved.' % songId
                        Find_Song_Switch_[0] = True
        except Exception, e:
            common.log('Find_Song_Link: ' + str(e))
    
    parser = HTMLParser()
    parser.handle_starttag = Find_Song_Link
    
    for k_ in artist_list:
        print 'start process artist %s ...' % k_
        Order_[0] = 0
        SongNameMap = {}
        s_ = 0
        Find_Song_Switch_[0] = True
        while(Find_Song_Switch_[0]):
            Find_Song_Switch_[0] = False
            raw_content = common.http_read(GetSongs_URL_Template_ % (s_, k_))
            s_ = s_ + 25
            if raw_content is None:
                continue
            try:
                raw_object = json.loads(raw_content)
            except Exception, e:
                common.log('json.loads: ' + str(e))
            try:
                raw_content = raw_object['data']['html']
            except Exception, e:
                common.log('extract html from json object: ' + str(e))
            try:
                raw_content = raw_content.decode('unicode_escape')
            except Exception, e:
                common.log('str.decode: ' + str(e)) 
            try:
                Artist_Id_ = k_
                parser.feed(raw_content)
                db_.add_artist_log(k_)
            except Exception, e:
                common.log('HTMLParser.feed: ' + str(e))
    
    return True    





