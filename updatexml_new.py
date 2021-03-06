import sys
import songs_api as api
import codecs
import urllib2
import simplejson
import re
from datetime import datetime, date, timedelta
import os
import shutil
import time
import glob
from multiprocessing import Pool
import traceback
import loggingmodule
from solr import SolrConnection
from solr.core import SolrException

#logging.basicConfig(format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s',level=logging.DEBUG, filename='errors.log')

def getMonths(currentPublishedDate):
	now = datetime.now()	
	m = re.search(re.compile("[0-9]{4}[-][0-9]{2}[-][0-9]{2}"),currentPublishedDate)
	n = re.search(re.compile("[0-9]{2}[:][0-9]{2}[:][0-9]{2}"),currentPublishedDate)
	ydate = m.group()+" "+n.group()
	dd = ydate
	yy = int(str(dd)[0:4])
	mm = int(str(dd)[5:7])
	total = (now.year-yy)*12+(now.month-mm)
	if total < 1:
		total = 1
	return total

def getCurrentTime():
	now = datetime.now()
	if(now.month<10):
		mm = '0'+str(now.month)
	else:
		mm = str(now.month)
	if(now.day<10):
		dd = '0'+str(now.day)
	else:
		dd = str(now.day)
	hh = now.hours
	mins = now.mins
def moveFiles(filename):
	fname = filename[filename.rfind('/')+1:]
	foldername = filename[:filename.rfind('/')]
	output_directory = foldername+'/deletedvideos'
	if(not os.path.exists(output_directory)):
		os.makedirs(output_directory)
	if(os.path.exists(os.path.join(output_directory, filename))):
		os.remove(os.path.join(output_directory, filename))
	shutil.move(filename,output_directory)	
def getDelta(oldDate,oldViewcount,newViewcount):
	now = datetime.now()
	days = (now - oldDate).days
	if(days == 0):
		return -1
	delta = (newViewcount - oldViewcount)/days
	return delta

def updateXml(filename):
	try:
		print filename
		try:
			oldsong = api.parse(filename)
		except Exception as e:
			logger_matrix.exception("Error")
			return
		videoUrl = "https://www.googleapis.com/youtube/v3/videos?id="+str(oldsong.youtubeId)+"&key=AIzaSyBE5nUPdQ7J_hlc3345_Z-I4IG-Po1ItPU&part=statistics,snippet,status"

		try:
			videoResult = simplejson.load(urllib2.urlopen(videoUrl),"utf-8")
		except Exception as e:
			print "error"
			logger_matrix.exception("Error loading json"+ videoUrl + "\n")
			return

		print "new values"
		if videoResult.has_key('items'):
			if(len(videoResult['items']) == 0):
				#fwrite_error.write("Error :No items returned "+ filename + "\n")
				logging.exception("Error :No items returned "+ filename + "\n")
				moveFiles(filename)
				return
			videoEntry = videoResult['items'][0]
			currentVideoViewCount = videoEntry['statistics']['viewCount']
			currentVideolikes = videoEntry['statistics']['likeCount']
			currentVideodislikes = videoEntry['statistics']['dislikeCount']
			currentVideoEmbedded = videoEntry['status']['embeddable']
			currentVideoStatus = videoEntry['status']['privacyStatus']
			currentPublishedDate = videoEntry['snippet']['publishedAt']
			if(currentVideoEmbedded == False or currentVideoStatus != 'public'):
				moveFiles(filename)
				return	
			if(int(currentVideolikes) !=0 and int(currentVideodislikes)!=0):
				currentVideorating = (float(currentVideolikes)*5)/(float(currentVideolikes)+float(currentVideodislikes))
			else:
				currentVideorating =0
		crawlHistoryList = oldsong.crawlHistoryList
		if(crawlHistoryList == None):
			crawlHistoryList = api.crawlHistoryList()
		crawlHistory = api.crawlHistory()

	#print oldsong.crawlDate.strftime("%Y-%m-%d")
		oldVideoRating = oldsong.rating
		if(oldVideoRating == None):
			oldVideoRating = 0
		crawlHistory.set_Views(oldsong.viewcount)
		crawlHistory.set_Date(oldsong.crawlDate.strftime("%Y-%m-%d"))
		currDelta = getDelta(oldsong.crawlDate,oldsong.viewcount,int(currentVideoViewCount))
		if(currDelta == -1):
			return
		crawlHistory.set_Delta(int(currDelta))
	#crawlHistory.add_stats(str(oldsong.viewcount)+':'+oldsong.crawlDate.strftime("%Y-%m-%d")+':'+str(oldVideoRating))
		crawlHistoryList.add_crawlHistory(crawlHistory)
		oldsong.set_rating(currentVideorating)
		oldsong.set_crawlDelta(currDelta)
		oldsong.set_crawlHistoryList(crawlHistoryList)
		oldsong.crawlDate =  datetime.now()
		oldsong.viewcountRate = float(currentVideoViewCount)/getMonths(currentPublishedDate)
		oldsong.viewcount = int(currentVideoViewCount)
                genreTag = oldsong.genreTag
                if(genreTag == None or genreTag == ''):
                    genreTag = GetgenreTag(oldsong)
                    oldsong.set_genreTag(genreTag)

		fx = codecs.open(filename,"w","utf-8")
		fx.write('<?xml version="1.0" ?>\n')
		oldsong.export(fx,0)
		fx.close()
	except Exception as e:
		logger_matrix.exception("Error")
		return

def GetgenreTag(oldsong):
    print 'getting genres tags'
    level1  = oldsong.level1Genres.genreName
    level2 = oldsong.level2Genres.genreName
    current_genres = []
    for g in level1:
        if(g.lower() not in current_genres):
            current_genres.append(g.lower())
    for g in level2:
        if(g.lower() not in current_genres):
            current_genres.append(g.lower())
    genre_tags = sorted(current_genres)
    combinedgenrestring = '@'.join(genre_tags)
    return combinedgenrestring

def updateGenreTags(filename):
    global connection_genre
    global connection_artist
    #response = connection.query(q="*:*",fq=[artistName],version=2.2,wt = 'json')
    #intersect = int(response.results.numFound)
    try:
        oldsong = api.parse(filename)

        print 'getting genres'
        try:
            genreTag = oldsong.genreTag
            if(genreTag == None or genreTag == ''):
                genreTag = GetgenreTag(oldsong)
                oldsong.set_genreTag(genreTag)
            artistId = 'artistName:"'+str(genreTag)+ '"'
            response_genre = connection_genre.query(q="*:*",fq=[artistId],version=2.2,wt = 'json')
            intersect = int(response_genre.results.numFound)
            if(intersect > 0):
                simGenreTagsList = api.similarGenresTagList()
                for result in response_genre.results:
                    currList = result['similarartistName']
                    currScores = result['similarCosineDistance']
                    currListId = result['similarartistId']
                    count = len(currList)
                    for i in range(0,count):
                        simGenreTag = api.similarGenreTag()
                        simGenreTag.set_genreTagName(currList[i])
                        simGenreTag.set_genreTagScore(currScores[i])
                        simGenreTag.set_genreTagId(int(currListId[i]))
                        simGenreTagsList.add_similarGenreTag(simGenreTag)
                    oldsong.set_similarGenresTagList(simGenreTagsList)
                    oldsong.set_genreTagId(int(result['artistId']))
        except Exception as e:
            logger_matrix.exception('genres writing error')
            logger_matrix.exception(e)

        print 'getting artists'
        try:
            artistId = oldsong.artistId
            artistId = 'artistId:"'+str(artistId)+ '"'
            print artistId
            response_artist = connection_artist.query(q="*:*",fq=[artistId],version=2.2,wt = 'json')
            intersect = int(response_artist.results.numFound)
            if(intersect > 0):
                print 'found it'
                similarArtistList = api.similarArtistList()
                for result in response_artist.results:
                    currList = result['similarartistName']
                    currScores = result['similarartistPopularityAll']
                    currListId = result['similarartistId']
                    count = len(currList)
                    for i in range(0,count):
                        similarArtist = api.similarArtist()
                        similarArtist.set_similarArtistName(currList[i])
                        similarArtist.set_similarArtistScore(currScores[i])
                        similarArtist.set_similarArtistId(int(currListId[i]))
                        similarArtistList.add_similarArtist(similarArtist)
                    oldsong.set_similarArtistList(similarArtistList)
                    #oldsong.set_genreTagId(int(result['artistId']))

        except Exception as e:
            logger_matrix.exception('artist writing error')
            logger_matrix.exception(e)
        fx = codecs.open(filename,"w","utf-8")
	fx.write('<?xml version="1.0" ?>\n')
	oldsong.export(fx,0)
	fx.close()
    
    except Exception as e:
        logger_matrix.exception(e)
	return
	
reload(sys)
sys.setdefaultencoding('utf8')

if __name__ == '__main__':
    logger_matrix = loggingmodule.initialize_logger('updatexmls.log')
    directory = raw_input("Enter directory: ")
    if not os.path.exists(directory):
        print 'directory doesnt exists'
        exit()
    m = raw_input("Enter m: ")
    m=int(m)
    choiceUpdate = int(raw_input("Enter 0 to update views \n 1 to update genretags and simartits\n"))
    filelist = list()
    t1=time.time()
    connection_genre = SolrConnection('http://aurora.cs.rutgers.edu:8181/solr/genretags')
    connection_artist = SolrConnection('http://aurora.cs.rutgers.edu:8181/solr/similar_artistsfromsongs')


    try:
        filelist = glob.glob(directory+"/*.xml")
        p =Pool(processes=int(m))
        if(choiceUpdate == 0):
            p.map(updateXml,filelist)
        else:
            #print filelist[8]
            p.map(updateGenreTags,filelist)
            #updateGenreTags(directory+"/0000bWXlOO0-l8k.xml")
        p.close()
        p.join()
    except Exception as e:
        logger_matrix.exception("Error")	

    print time.time()-t1
