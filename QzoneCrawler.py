#-*- coding: UTF-8 -*-

from socket import*
import time
import os
import re
from ctypes import cdll
import gzip
import json

# httpx module from -> https://github.com/thisforeda/socket-http
import httpx

#-------------------------------------------------------------------------------------#
#                   (C) 2015 by ZhangYiDa <http://www.loogi.cn>                       #
#                              All Rights Reserved.                                   #
#-------------------------------------------------------------------------------------#
MINIMUM       =  255
STR_JSONDEC_ERROR =  "JSON 解码失败"
STR_ENCODE_ERROR  =  "UNICODE编码失败"
STR_ENCODE_ERROR  =  "UNICODE编码失败"

CRLF              =  b'\r\n\r\n'


class Crawler:
    def __init__(self):
        self.basedir         =   ''
        self.__log_file      =   self.__new_file_name('crawler-')
        self.cookie = ''
        self.main_page_cgi_url = 'http://user.qzone.qq.com/cgi-bin/main_page_cgi?uin=%s&param=15|16&g_tk=%s'
        self.feeds_html_act_url = 'http://ic2.qzone.qq.com/cgi-bin/feeds/feeds_html_act_all?hostuin=%s&start=%s&count=%s&g_tk=%s'
        self.emotion_cgi_msglist_url = 'http://taotao.qq.com/cgi-bin/emotion_cgi_msglist_v6?uin=%s&pos=%s&num=%s&g_tk=%s'

        
    def __write(self,str):
        '''
        一个简单的日志记录过程 '''
        with open(self.__log_file,'a+') as hfile:
            str = time.asctime() + ':' + str + os.linesep
            hfile.write( str )

    def calc_GTK(self,cookie):
        if type(cookie) is not str:
            if type(cookie) is not bytes:
                return None
            cookie = str(self.__safeenc(cookie))
        '''
          在js的g_tk构造函数中貌似优先使用p_skey计算g_tk
          如果没有则用skey,不知道分析的对不对,没学过JS
          下面一段代码就是在COOKIE中查找 skey 的值
        '''
        match = re.search('(?i)p_skey=(.*?);',cookie)
        if match is None:
            match = re.search('(?i)skey=(.*?);',cookie)
            if match is None:
                match = re.search('(?i)rv2=(.*?);',cookie)
                if match is None:
                    return None
        '''将值转换为字节码,貌似字节参数可以直接传给自己写的DLL函数'''
        try :
            skey = match.groups()[0].encode('utf-8')
            ''' 调用DLL来计算g_tk的int值 '''
            return str(self.getACSRFToken(skey))
        except Exception as err:
            self.__write(str(err))
            return None
    def getACSRFToken(self,skey):
        var_hash = 5381
        for i in range(0,len(skey)):
            var_hash += (var_hash<<5) + skey[i]
        return var_hash & 2147483647
    
    def __new_file_name(self,prefix):
        ctime = time.localtime()
        stime =   str(ctime.tm_year) +  '_' \
                + str(ctime.tm_mon)  +  '_' \
                + str(ctime.tm_mday) +  '_' \
                + str(ctime.tm_hour) +  '_' \
                + str(ctime.tm_min)  +  '_' \
                + str(ctime.tm_sec)  +  '.EDA'
        if type(prefix) is not str:
            if type(prefix) is not int:
                return None
            prefix = str(prefix)
        return self.basedir + prefix + '@' + stime

        
    def __fmtqum(self,qnum):
        if type(qnum) is not str:
            if type(qnum) is not int:
                return None
            return str(qnum)

    
    def how_many_shuoshuo(self,qnum):
        cookie = self.cookie
        if type(cookie) is not str and cookie:
            cookie = str(cookie)
        g_tk = self.calc_GTK(cookie)
        if g_tk is not None:
            qnum = self.__fmtqum(qnum)
            '''获取说说数量的地址和说说JSON的地址不一样'''
            ret = httpx.urlopen(
                self.main_page_cgi_url%(qnum,g_tk),
                custom_header={'Cookie':cookie}
                )
            
            if not hasattr(ret,'data'):
                return -2
            '''返回-1代表无权访问,返回值代表说说数量,返回-2代表。自己猜'''
            match = re.search('"SS":(\d+)',self.__safedec(ret.data))
            if match is not None:
                return int(match.groups()[0])
            return -1
        return -2
        
    def get_shuoshuo_by_feeds_html_act(self,qnum):
        '''从什么位置开始'''
        startpos   =   0
        '''每次请求的数量'''
        distance   =   10
        '''输出文件的名称'''
        cookie = self.cookie
        if type(cookie) is not str and cookie:
            cookie = str(cookie)
        g_tk = self.calc_GTK(cookie)
        if g_tk is not None:
            outname    =   self.__new_file_name(qnum)
            if outname is not None:
                while True:
                    ''' 说说从0开始,每次最低请求6个,不论怎样,只有多没有少
                       start=0;cnt=6
                    '''  
                    #print("startpos=%d  distance=%d"%(startpos,distance))
                    startpos += distance
                    ret = httpx.urlopen(
                        self.feeds_html_act_url%(qnum,startpos,distance,g_tk),
                        custom_header = {'Cookie':cookie}
                        )
                    if hasattr(ret,'data'):
                        with open(outname,'ab') as streamout:
                            streamout.write(ret.data + CRLF + CRLF)
                        '''如果在JSON中找到了这个代表没有说说可获取'''
                        if re.search('(?i)hasMoreFeeds_0:false',self.__safedec(ret.data)):
                            break
                    else:
                        return False
                streamout.close()
                return True
        return False

    def __parse_callback_json(self,data):
        '''去除数据的_callback( json );'''
        data = data[10:-2]
        if type(data) is bytes:
            data = self.__safedec(data)
        '''
           使用JSON 提取所有在说说中有评论的人并 以 {QQ:NAME} 格式保存到字典中
           这个功能并不是很完善,下面只是我在3个人的说说中发现的 JSON 关系
        '''
        try :
            Jsondata = json.loads(data)
        except Exception as err:
            self.__write(STR_JSONDEC_ERROR)
            return False
        if Jsondata.get('msglist'):
            for msg in Jsondata['msglist']:
                if msg.get('rtlist'):
                    for rt in msg['rtlist']:
                        if rt.get('name'):
                            self.dicts.update({rt['uin']:rt['name']})
                            if rt.get('conlist'):
                                for at in rt['conlist']:
                                    if at.get('nick'):
                                        self.dicts.update({at['uin']:at['nick']})
                elif msg.get('commentlist'):
                    for comment in msg['commentlist']:
                        if comment.get('name'):
                            self.dicts.update({comment['uin']:comment['name']})
                        if comment.get('list_3'):
                            for li in comment['list_3']:
                                if li.get('name'):
                                    self.dicts.update({li['uin']:li['name']})
                else:
                    continue
                    #self.__write(str(msg.keys()))
            return True
        return False
        
    
    ''' '''
    def get_shuoshuo_emotion_cgi_msglist(self,qnum):
        '''从什么位置开始'''
        startpos   =   0
        '''每次请求的数量'''
        distance   =   10
        '''输出文件的名称'''
        cookie = self.cookie
        if type(cookie) is not str and cookie:
            cookie = str(cookie)
        g_tk = self.calc_GTK(cookie)
        if g_tk is not None:
            outname    =   self.__new_file_name(qnum)
            isFirstRun =   True
            if outname is not None:
                while True:
                    #print("startpos=%d  distance=%d"%(startpos,distance))
                    ret = httpx.urlopen(
                        self.emotion_cgi_msglist_url%(qnum,startpos,distance,g_tk),
                        custom_header = {'Cookie':cookie}
                        )
                    if hasattr(ret,'data'):
                        '''------------数据大小检查-----------'''
                        if len(ret.data) < MINIMUM:
                            self.__write(self.__safedec(ret.data))
                            print("返回数据小于最低值,请先检查日志")
                            while True:
                                cmd = input("指令:")
                                if cmd == "continue":
                                    break
                                elif cmd == "exit":
                                    return False
                                elif cmd == "cookie":
                                    self.cookie = input("Cookie:")
                                    break
                        '''----------------------------------'''
                        if isFirstRun:
                            match = re.search('(?i)\"msgnum\":(\d+)',self.__safedec(ret.data))
                            if match is not None:
                                shuoshuo_cnt = int(match.groups()[0])
                                if shuoshuo_cnt == 0:
                                    return False
                                isFirstRun   = False
                                print("user %d has %d shuoshuo,now crawling"%(qnum,shuoshuo_cnt))
                            else: return False
                        with open(outname,'ab') as streamout:
                            streamout.write(ret.data + CRLF*2)
                            self.__parse_callback_json(ret.data)
                        startpos += distance
                        if startpos >= shuoshuo_cnt:
                            break
                    else:
                        return False
                streamout.close()
                return True
        return False
    
    def __safedec(self,what):
        try : 
            return what.decode('utf-8')
        except UnicodeDecodeError:
            try :
                return what.decode('gbk')
            except UnicodeDecodeError:
                self.__write(STR_ENCODE_ERROR)
        return ''
    
    def __safeenc(self,what):
        try : 
            return what.encode('utf-8')
        except UnicodeEncodeError:
            try :
                return what.encode('gbk')
            except UnicodeEncodeError:
                self.__write(STR_ENCODE_ERROR)
        return b''

def main_thread():
    crawler = Crawler()
    crawler.basedir = os.getcwd() + '\\crawler\\'
    crawler.cookie = 'YOUR COOKIE'
    
    with open('friends.dat','rb') as hfriend:
        for line in hfriend:
            if line == '\n':
               continue
            try :
                QQ = int(line.decode('utf-8').split('#')[0])
            except Exception as err:
                continue
            startT = time.clock()
            crawler.dicts = {}
            ret = crawler.get_shuoshuo_emotion_cgi_msglist(QQ)
            if ret == False:
                print("failed craw %s, access denied or no shuoshuo to craw"%QQ)
                continue
            print("time used= %d"%(time.clock() - startT))
            with open(crawler.basedir + str(QQ) + '.dat','wb') as hf:
                for (key,value) in crawler.dicts.items():
                    key  = str(key).encode('utf-8')
                    value = value.encode('utf-8')
                    data  = key + b' # ' + value + b'\r\n'
                    hf.write(data)

main_thread()

