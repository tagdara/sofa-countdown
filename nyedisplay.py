#!/usr/bin/python3
import os
import pygame
import pygame.display
import sys
import datetime
import time
import io
import signal
import urllib.parse
from urllib.request import urlopen

import ctypes
import re
import subprocess
import logging
from logging.handlers import RotatingFileHandler
import paho.mqtt.client as paho
import random
import json
import ssl
        
class framebufferDisplay(object):

    def __init__ (self):
        self.config=self.loadJSON('config')
        self.logsetup(self.config['log_path'])
        self.running=True
        self.sonosdata={ "title":"None", "creator":"None", "transport_state":"None"}
        self.logomode="nowplaying"
        self.logomodes=["nowplaying","countdown"]
        self.sonosplayer="None"
        
        self.running=True
        self.burnflip=False
        self.exitRequest=False
        self.fontsizer="up"
        self.fontstep=50
        self.pollstep=.1
        self.pulsetime=30
        #self.eventtime= datetime.datetime.now()+datetime.timedelta(0,5)
        self.eventtime= datetime.datetime.strptime(self.config['event_time'], '%b %d %Y, %I:%M:%S%p')
        self.toggle=datetime.datetime.now()
        self.toggletime=60
        
        #self.eventtime=datetime.datetime.now()+datetime.timedelta(0,5)

    def start(self):
        try:
            #OMG a fix for the little incompatibilities: http://stackoverflow.com/questions/39198961/pygame-init-fails-when-run-with-systemd
            self.log.info('Setting up sighup capture')
            signal.signal(signal.SIGHUP, self.sighuphandler)
        except AttributeError:
            # Windows compatibility
            pass
        
        self.log.info('Setting up framebuffer')
        result=self.setupfbdriver()
        self.log.info('Defining pygame screen')
       
        self.screen=self.getPygameScreen()
        self.log.info('Getting screen resolution')
        self.clearscreen()
        self.log.info('Starting logo display')
        self.showlogo()
        self.lastflip=time.time()
        self.playpause=True
        self.mqttclient=paho.Client(self.config["mqtt_client_name"]) #create client object 
        self.mqttclient.on_message=self.on_message
        self.mqttclient.connect(self.config["mqtt_server"]) #establish connection 
        self.mqttclient.loop_start()
        self.mqttclient.subscribe(self.config["mqtt_channel"]) #subscribe
        self.mainloop()
        self.mqttclient.disconnect() #disconnect
        self.mqttclient.loop_stop() #stop loop
        return True
        
    def loadJSON(self, jsonfilename):
        
        try:
            configdir=os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
            with open('%s/%s.json' % (configdir, jsonfilename),'r') as jsonfile:
                return json.loads(jsonfile.read())
        except:
            self.log.error('Error loading json: %s' % jsonfilename,exc_info=True)
            return {}    
            
    #define callback
    def on_message(self, client, userdata, message):
        
        try:
            self.log.info("received message: %s " % message.payload.decode("utf-8"))
            alexamsg=json.loads(message.payload.decode("utf-8"))
            if alexamsg['event']['endpoint']['endpointId'].startswith("sonos:player:"):
                playerid=alexamsg['event']['endpoint']['endpointId'].split(':')[2]
                if self.config["player_id"]==playerid:
                    self.log.info('Sonos Update: %s' % alexamsg['context']['properties'])
                    sonosprops={}
                    try:
                        for prop in alexamsg['context']['properties']:
                            sonosprops[prop['name']]=prop['value']
                    except:
                        pass
                    try:
                        for prop in alexamsg['payload']['change']['properties']:
                            sonosprops[prop['name']]=prop['value']
                    except:
                        pass
                    self.sonosdata=sonosprops
                    self.log.info('Sonos Update: %s' % sonosprops)

                    self.sonosplaying=True
                    self.toggle=datetime.datetime.now()
                    self.switchMode("nowplaying")

        except:
            self.log.error('Error with mqtt data.', exc_info=True)

    def mainloop(self):
        try:
            while not self.exitRequest:
                if self.eventtime>datetime.datetime.now():
                    delta=self.eventtime-datetime.datetime.now()
                    if delta.seconds<self.config["countdown_lock"]:
                        self.logomode="countdown"
                self.updateDisplay()
                time.sleep(self.pollstep)
        except:
            self.log.error('Exiting on error', exc_info=True)

    def sighuphandler(self,signum, frame):
        self.log.info('Sighup received, but ignoring')
        pass

    def logsetup(self, logbasepath, level="INFO"):

        logname="sofa-display"
        log_formatter = logging.Formatter('%(asctime)-6s.%(msecs).03d %(levelname).1s%(lineno)4d: %(message)s','%m/%d %H:%M:%S')
        logpath=os.path.join(logbasepath, logname)
        logfile=os.path.join(logpath,"%s.log" % logname)
        loglink=os.path.join(logbasepath,"%s.log" % logname)
        if not os.path.exists(logpath):
            os.makedirs(logpath)
        #check if a log file already exists and if so rotate it

        needRoll = os.path.isfile(logfile)
        log_handler = RotatingFileHandler(logfile, mode='a', maxBytes=1024*1024, backupCount=5)
        log_handler.setFormatter(log_formatter)
        log_handler.setLevel(getattr(logging,level))
        if needRoll:
            log_handler.doRollover()
            
        console = logging.StreamHandler()
        console.setFormatter(log_handler)
        console.setLevel(logging.INFO)
        
        logging.getLogger(logname).addHandler(console)

        self.log =  logging.getLogger(logname)
        self.log.setLevel(logging.INFO)
        self.log.addHandler(log_handler)
        if not os.path.exists(loglink):
            os.symlink(logfile, loglink)
        
        self.log.info('-- -----------------------------------------------')


    def processExit(self):
        self.log.info('Terminating pygame for shutdown')
        pygame.quit()

    def processCEC(self,mdata):
        
        pass
        # This is currently stubbed out and needs to be replaced from the older code
        # that moved CEC to another module

 
    def updateDisplay(self):

        try:
            if datetime.datetime.now()<self.eventtime and datetime.datetime.now() > self.toggle+datetime.timedelta(0,self.toggletime) and self.logomode!='countdown':
                self.clearscreen()
                self.logomode="countdown"

            if time.time() > self.lastflip+60 and self.logomode=="nowplaying":
                self.clearscreen()
                self.burnflip=not self.burnflip
                self.lastflip=time.time()
                self.showlogo()
            elif self.logomode=="countdown":
                self.showlogo()
            else:
                self.updateTime()
                        
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    if event.key==pygame.K_ESCAPE:
                        #self.forwardevent('command','keypress',{"key":"esc"})
                        self.exitRequest=True
                    elif event.key==pygame.K_RIGHT:
                        #self.forwardevent('command','keypress',{"key":"right"})
                        self.switchMode('up')
                    elif event.key==pygame.K_LEFT:
                        #self.forwardevent('command','keypress',{"key":"left"})
                        self.switchMode('down')
                    elif event.key==pygame.K_SPACE:
                        #self.burnflip=not self.burnflip
                        self.showlogo()

        except:
            self.log.error('Error processing pygame events',exc_info=True)

    def setupfbdriver(self):
    
        try:
            self.log.info('Setting up framebuffer device.')
            found=False
            drivers = ('directfb', 'fbcon', 'svgalib')
            os.putenv('SDL_FBDEV','/dev/fb0')
            os.environ["SDL_FBDEV"] = "/dev/fb0"
            os.putenv('SDL_NOMOUSE','1')
            for driver in drivers:
                self.log.info('Trying driver: %s' % driver)
                if not os.getenv('SDL_VIDEODRIVER'):
                    os.putenv('SDL_VIDEODRIVER',driver)
                try:
                    pygame.display.init()
                except pygame.error:
                    self.log.error('Pygame init error', exc_info=True)
                    continue
                found = True
                break
            if not found:
                raise Exception('No suitable video driver found.')
            
            return found
        except:
            self.log.error('Error with pygame display init process'+str(sys.exc_info()[2]))
            return None

    def getPygameScreen(self):
        pygame.display.init()
        self.log.info('Screen size: '+str(pygame.display.Info().current_w)+'x'+str(pygame.display.Info().current_h))
        if pygame.display.Info().current_w > 1920:
            size = (800, 480)
            screen = pygame.display.set_mode(size)
        else:
            size = (pygame.display.Info().current_w, pygame.display.Info().current_h)
            screen = pygame.display.set_mode(size, pygame.FULLSCREEN)
        self.dsize=size
        self.log.info('Launching pygame init')
        pygame.init()
        pygame.display.set_caption('TV UI')
        background = pygame.Surface(screen.get_size())
        background = background.convert()
        background.fill((250, 250, 250))
        pygame.mouse.set_visible(0)
        pygame.display.update()
        self.log.info('Completing pygame screen setup')
        return screen


    def showText(self,showtext=""):
        # render text
        myfont = pygame.font.Font(self.config['font_file'], 48)
        fs=myfont.size(showtext)
        label = myfont.render(str(showtext), 1, (128,128,128), (0,0,0))
        self.screen.blit(label, ((800-fs[0])/2, (480-fs[1])/2))
        pygame.display.update()

    def showTime(self):
        # render text
        current_time = datetime.datetime.now()
        showtime=current_time.strftime("%I:%M")
        myfont = pygame.font.Font(self.config['font_file'], 48)
        fs=myfont.size(showtime)
        label = myfont.render(str(showtime), 1, (128,128,128), (0,0,0))
        self.screen.blit(label, ((self.dsize[0]-fs[0])/2, 10))
        pygame.display.update()


    def drawText(self, surface, text, color, rect, font, aa=True, bkg=None):

        rect = pygame.Rect(rect)
        y = rect.top
        lineSpacing = -2
        # get the height of the font
        fontHeight = font.size("Tg")[1]
 
        while text:
            i = 1
 
            # determine if the row of text will be outside our area
            if y + fontHeight > rect.bottom:
                break
 
            # determine maximum width of line
            while font.size(text[:i])[0] < rect.width and i < len(text):
                i += 1
 
            # if we've wrapped the text, then adjust the wrap to the last word      
            if i < len(text): 
                i = text.rfind(" ", 0, i) + 1
 
            # render the line and blit it to the surface
            if bkg:
                image = font.render(text[:i], 1, color, bkg)
                image.set_colorkey(bkg)
            else:
                image = font.render(text[:i], aa, color)
 
            surface.blit(image, (rect.left, y))
            y += fontHeight + lineSpacing
 
            # remove the text we just blitted
            text = text[i:]
 
        return text
        
    def sonosNotPlaying(self):

        sonoslogo = pygame.image.load(self.config['not_playing_logo'])
        isize = sonoslogo.get_size()
        logodiff=(self.dsize[0]/3)/isize[0]
        sonoslogo = pygame.transform.smoothscale(sonoslogo, (int(isize[0]*logodiff),int(isize[1]*logodiff)))
        isize = sonoslogo.get_size()
        xp = (self.dsize[0] - isize[0]) / 2  # find location to center image on screen
        yp = (self.dsize[1] - isize[1]) / 2
        self.screen.blit(sonoslogo,(xp,yp))    
        myfont = pygame.font.Font(self.config['font_file'], 48)
        showtext="Not currently playing."
        fs=myfont.size(showtext)
        label = myfont.render(str(showtext), 1, (240,240,240), (0,0,0))
        self.screen.blit(label, ((self.dsize[0]-fs[0])/2, (yp/2)+(self.dsize[1]/2)))
        pygame.display.update()


    def sonosNowPlaying(self, song, artist, rightpos=False):
       
        try:
            #scale and render cover art
            coverart=self.sonosCoverArt()
            coverart = pygame.transform.smoothscale(coverart, (int(self.dsize[1]*0.8),int(self.dsize[1]*0.8)))
            isize = coverart.get_size()
            
            #center on half
            xp = ((self.dsize[0]/2) - isize[0])-10
            #xp = (self.dsize[0] - isize[0]) / 2  # find location to center image on screen
            yp = (self.dsize[1] - isize[1]) / 2
            
            if self.burnflip:
                self.screen.blit(coverart,((self.dsize[0]/2)+10,yp))    
                textarea = pygame.Rect((xp, yp, isize[0], isize[1]))
            else:
                self.screen.blit(coverart,(xp,yp))
                textarea = pygame.Rect(((self.dsize[0]/2)+10, yp, isize[0], isize[1]))
    
            #scale and render title and artist
            songfont = pygame.font.Font(self.config['font_file'], int(self.dsize[0]/16))
            songcolor=(240,240,240)
            artistfont = pygame.font.Font(self.config['font_file'],  int(self.dsize[0]/18))
            artistcolor=(180,180,180)
    
            self.drawSongData(song,artist,songcolor,artistcolor,textarea,songfont,artistfont,self.burnflip)
            pygame.display.update()    
        except:
            self.log.error('Error displaying now playing data', exc_info=True)
        

    def sonosCoverArt(self):
        
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            image_url="https://%s%s" % (self.config['mqtt_server'], urllib.parse.quote(self.sonosdata['art']))
            self.log.info('Retrieving album art from '+str(image_url))
            image_str = urlopen(image_url, context=ctx).read()
            image_file = io.BytesIO(image_str)
            image1 = pygame.image.load(image_file)
            return image1
        except:
            image1 = pygame.image.load(self.config['not_playing_logo'])
            self.log.error('Error getting album image',exc_info=True)
            return image1
        

    def drawSongData(self, song, artist, songcolor, artistcolor, rect, songfont, artistfont, aright=False, aa=True, bkg=None):
        
        try:
            rect = pygame.Rect(rect)
            bg=(0,0,0)
            pygame.draw.rect(self.screen,bg,(rect.left,rect.top,rect.width,rect.height))

            y = rect.top
            lineSpacing = -40
            lineSpacing = 0
            # get the height of the font
            font=songfont
            fontHeight = font.size("T")[1]
            lines=[]
    
            text=song
            while text:
                i = 1
                # determine if the row of text will be outside our area
                if y + fontHeight > rect.bottom:
                    break
                # determine maximum width of line
                while font.size(text[:i])[0] < rect.width and i < len(text):
                    i += 1
 
                # if we've wrapped the text, then adjust the wrap to the last word      
                if i < len(text): 
                    i = text.rfind(" ", 0, i) + 1
 
                # render the line and blit it to the surface
                if bkg:
                    image = font.render(text[:i].strip(), 1, songcolor, bkg)
                    image.set_colorkey(bkg)
                else:
                    image=font.render(text[:i].strip(), aa, songcolor)
            
                linedata={}
                linedata['text']=text[:i].strip()
                linedata['image']=image
                linedata['width']=font.size(linedata['text'])[0]
                text = text[i:]
                if text:
                    linedata['fontheight']=fontHeight+lineSpacing
                else:
                    linedata['fontheight']=fontHeight
        
                lines.append(linedata)
 
                #surface.blit(image, (rect.left, y))
                y += fontHeight + lineSpacing
                # remove the text we just blitted

            lineSpacing = 0
            text=artist
            font=artistfont
            artistlines=[]
            fontHeight = font.size("Tg")[1]

            while text:
                i = 1
                # determine if the row of text will be outside our area
                if y + fontHeight > rect.bottom:
                    break
                # determine maximum width of line
                while font.size(text[:i])[0] < rect.width and i < len(text):
                    i += 1
 
                # if we've wrapped the text, then adjust the wrap to the last word      
                if i < len(text): 
                    i = text.rfind(" ", 0, i) + 1
 
                # render the line and blit it to the surface
                if bkg:
                    image = font.render(text[:i].strip(), 1, artistcolor, bkg)
                    image.set_colorkey(bkg)
                else:
                    image=font.render(text[:i].strip(), aa, artistcolor)
        
                linedata={}
                linedata['text']=text[:i].strip()
                linedata['image']=image
                linedata['width']=font.size(linedata['text'])[0]
                text = text[i:]
                if text:
                    linedata['fontheight']=fontHeight+lineSpacing
                else:
                    linedata['fontheight']=fontHeight
        
                lines.append(linedata)
                #surface.blit(image, (rect.left, y))
                y += fontHeight + lineSpacing
                # remove the text we just blitted

            currentpos=0
            for line in lines:
                if aright:
                    self.screen.blit(line['image'], (rect.right-line['width'], (rect.top+(rect.height-y)/2)+currentpos))
                else:
                    self.screen.blit(line['image'], (rect.left, (rect.top+(rect.height-y)/2)+currentpos))
                currentpos=currentpos+line['fontheight']

            return text
        except:
            self.log.error('Error drawing Song data',exc_info=True)

    def nplogo(self):
        try:
            self.log.info('Displaying Now Playing Logo')
            self.log.info(str(self.sonosdata))
            self.sonosplaying=False
            self.log.info('Checking: %s' % self.sonosdata )
            if ('title' in self.sonosdata) and ('artist' in self.sonosdata):
                if str(self.sonosdata['title'])!="None" and str(self.sonosdata['artist'])!="None":
                    self.log.info('Sonos playing: %s/%s' % (self.sonosdata['title'],self.sonosdata['artist']))
                    self.sonosNowPlaying(self.sonosdata['title'], self.sonosdata['artist'])
                    self.sonosplaying=True

            if not self.sonosplaying:
                self.sonosNotPlaying()
        except:
            self.log.error('Error displaying now playing data', exc_info=True)

    def cdlogo(self):

        self.clearscreen()
        datecolor=(240,240,240)
        delta=self.eventtime - datetime.datetime.now()
        basefontsize=self.config['base_font_size']
        hours, minsec=divmod(int(delta.seconds), 3600)
        mins, secs = divmod(int(minsec), 60)
        if self.eventtime>datetime.datetime.now():
            if delta.days>0:
                showtext = '{:01d}:{:02d}:{:02d}:{:02d}'.format(delta.days,hours,mins, secs)
            elif hours>0:
                showtext = '{:01d}:{:02d}:{:02d}'.format(hours,mins, secs)
            elif mins>0:
                showtext = '{:01d}:{:02d}'.format(mins, secs)
            elif secs>0:
                showtext = '{:01d}'.format(secs)
            else:
                datecolor=(random.randint(50,255),random.randint(50,255),random.randint(50,255))
                showtext = '2019'
                
        else:
            showtext = '2019'
            howfarpast=datetime.datetime.now()-self.eventtime
            if howfarpast.seconds<self.pulsetime:
                datecolor=(random.randint(50,255),random.randint(50,255),random.randint(50,255))
                if self.fontsizer=="up":
                    if self.bigfontsize>self.config['base_font_size']:
                        self.fontsizer="down"
                        self.bigfontsize=self.bigfontsize-self.fontstep
                    else:
                        self.bigfontsize=self.bigfontsize+self.fontstep
                else:
                    if self.bigfontsize<int(self.config['base_font_size']/2):
                        self.fontsizer="up"
                        self.bigfontsize=self.bigfontsize+self.fontstep
                    else:
                        self.bigfontsize=self.bigfontsize-self.fontstep
            else:
                self.bigfontsize=self.config['base_font_size']
                
            basefontsize=self.bigfontsize

        myfont = pygame.font.Font(self.config['font_file'], basefontsize)
        fs=myfont.size(showtext)
        xp = (self.dsize[0] - fs[0]) / 2  # find location to center image on screen
        yp = (self.dsize[1] - fs[1]) / 2
        dfs = self.dynamic_font_size(str(showtext), basefontsize, self.dsize[0]*.8)
        myfont = pygame.font.Font(self.config['font_file'], dfs)

        fs=myfont.size(showtext)
        xp = (self.dsize[0] - fs[0]) / 2  # find location to center image on screen
        yp = (self.dsize[1] - fs[1]) / 2
        label = myfont.render(str(showtext), 1, datecolor, (0,0,0))
        self.screen.blit(label, (xp,yp))   
        pygame.display.update()

    def updateTime(self):

        myfont = pygame.font.Font(self.config['font_file'], 48)
        current_time = datetime.datetime.now()
        showtime=current_time.strftime("%I:%M").lstrip('0')
        fs=myfont.size(showtime)

        label = myfont.render(str(showtime), 1, (240,240,240), (0,0,0))
        self.screen.blit(label, ((self.dsize[0]-fs[0])/2, 5))


    def dynamic_font_size(self, text, size, width, dec_by=1):
        font = pygame.font.Font(self.config['font_file'], size)
        if font.size(text)[0] > width:
            return self.dynamic_font_size(text, size-dec_by, width, dec_by)
        #return font.render(text, aa, color)
        return size

    def clearscreen(self):
        bgc=(0,0,0)
        my_rect = pygame.Rect((0, 0, self.dsize[0],self.dsize[1]))
        pygame.draw.rect(self.screen,bgc,my_rect)
        
    def showlogo(self):

        try:
            if self.logomode=="nowplaying":
                self.nplogo()
            elif self.logomode=="countdown":
                self.cdlogo()
            else:
                self.log.error('WARNING: Showlogo got an unrecognized mode: '+str(self.logomode))     
        except:
            self.log.error('Error showing logo.',exc_info=True)
        
    def switchMode(self,newmode):

        self.toggle=datetime.datetime.now()
        if self.logomode in self.logomodes:
            modeindex=self.logomodes.index(self.logomode)
        else:
            modeindex=0
        oldmodeindex=modeindex
        
        if newmode in self.logomodes:
            modeindex=self.logomodes.index(newmode)
        elif newmode=="up":
            modeindex=modeindex+1
        elif newmode=="down":
            modeindex=modeindex-1
        
        if modeindex<0:
            modeindex=0
            
        if modeindex>len(self.logomodes)-1:
            modeindex=len(self.logomodes)-1
        
        self.logomode=self.logomodes[modeindex]
        self.log.info('Switching mode: '+str(self.logomode))
        self.clearscreen()
        self.showlogo()   
 
if __name__ == '__main__':
    fbd=framebufferDisplay()
    fbd.start()
