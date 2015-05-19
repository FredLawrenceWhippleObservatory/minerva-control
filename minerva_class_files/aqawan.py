'''basic Aqawan control class, writes log to aqawan_(1 or 2).log file
create class object by aqawan(aqawan_num), where aqawan_num specify which aqawan
test program creates aqawan(1) object and send keyboard commands'''

import time, telnetlib, socket, threading, logging, ipdb, datetime, json
from configobj import ConfigObj
import minerva_class_files.mail as mail

#To Do: change log to appropriate format, log open/close failure by reading status, add more functionality as needed 
class aqawan:

    #aqawan class init method, create an aqawan object by passing either 1 or 2 to specify which aqawan
    def __init__(self,aqawan_num, night, configfile=''):

        self.num = aqawan_num

        #set appropriate parameter based on aqawan_num
        #create configuration file object 
        configObj = ConfigObj(configfile)        
        try:
            aqawanconfig = configObj[self.num]
        except:
            print('ERROR accessing ', self.num, ".", 
               self.num, " was not found in the configuration file", configfile)
            return 

        self.IP = aqawanconfig['Setup']['IP']
        self.PORT = aqawanconfig['Setup']['PORT']
        logger_name = aqawanconfig['Setup']['LOGNAME']
        log_file = 'logs/' + night + '/' + aqawanconfig['Setup']['LOGFILE']
        self.telescopes = aqawanconfig['Setup']['TELESCOPES']
        self.currentStatusFile = 'current_' + aqawan_num + '.log'
                
        # setting up aqawan logger
        fmt = "%(asctime)s [%(filename)s:%(lineno)s - %(funcName)s()] %(levelname)s: %(message)s"
        datefmt = "%Y-%m-%dT%H:%M:%S"

        self.logger = logging.getLogger(logger_name)
        formatter = logging.Formatter(fmt,datefmt=datefmt)
        formatter.converter = time.gmtime
        
        fileHandler = logging.FileHandler(log_file, mode='a')
        fileHandler.setFormatter(formatter)

        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(logging.INFO)
        
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(fileHandler)
        self.logger.addHandler(console)
        
        self.isOpen = False
        self.mailsent = False
        self.lastClose = datetime.datetime.utcnow() - datetime.timedelta(days=1)

        #start heartbeat thread, create lock object to prevent multiple PAC connection at same time
        self.h_thread = threading.Thread(target=self.heartbeat, args=())
        self.lock = threading.Lock()
        self.h_thread.start()
            
    #heartbeat thread function
    def heartbeat(self):
        return self.send('HEARTBEAT')

    def crack(self):
        self.send('OPEN_SHUTTER_1')
        self.send('STOP')

    #send message to aqawan
    def send(self,message):
            
        messages = ['HEARTBEAT','STOP','OPEN_SHUTTERS','CLOSE_SHUTTERS',
                    'CLOSE_SEQUENTIAL','OPEN_SHUTTER_1','CLOSE_SHUTTER_1',
                    'OPEN_SHUTTER_2','CLOSE_SHUTTER_2','LIGHTS_ON','LIGHTS_OFF',
                    'ENC_FANS_HI','ENC_FANS_MED','ENC_FANS_LOW','ENC_FANS_OFF',
                    'PANEL_LED_GREEN','PANEL_LED_YELLOW','PANEL_LED_RED',
                    'PANEL_LED_OFF','DOOR_LED_GREEN','DOOR_LED_YELLOW',
                    'DOOR_LED_RED','DOOR_LED_OFF','SON_ALERT_ON',
                    'SON_ALERT_OFF','LED_STEADY','LED_BLINK',
                    'MCB_RESET_POLE_FANS','MCB_RESET_TAIL_FANS',
                    'MCB_RESET_OTA_BLOWER','MCB_RESET_PANEL_FANS',
                    'MCB_TRIP_POLE_FANS','MCB_TRIP_TAIL_FANS',
                    'MCB_TRIP_PANEL_FANS','STATUS','GET_ERRORS','GET_FAULTS',
                    'CLEAR_ERRORS','CLEAR_FAULTS','RESET_PAC']
        # not an allowed message
        if not message in messages:
            self.logger.error('Message not recognized: ' + message)
            return -1
        
        port = 22004
        self.lock.acquire()
        try:
            tn = telnetlib.Telnet(self.IP,port,1)
        except socket.timeout:
            self.logger.error('Timeout attempting to connect to the aqawan')
            self.lock.release()
            return -1

        tn.write("vt100\r\n")

        # why is this necessary!? this is quite unsettling
        response = ''
        while response == '':
            tn.write(message + "\r\n")
            response = tn.read_until(b"/r/n/r/n#>",0.5)
            
        tn.close()
        self.lock.release()
        return response

    #open both shutters
    def open_both(self):

        self.logger.info('Shutting off lights')
        response = self.send('LIGHTS_OFF')
        if response == -1:
            self.logger.error('Could not turn off lights')

        self.logger.info('Opening shutter 1')
        response = self.open_shutter(1)
        if response == -1: return -1
        self.logger.info('Shutter 1 open')

        self.logger.info('Opening shutter 2')
        response = self.open_shutter(2)
        if response == -1: return -1
        self.logger.info('Shutter 2 open')

        self.isOpen = True
            
    def open_shutter(self,shutter):
        # make sure this is an allowed shutter
        if shutter not in [1,2]:
            self.logger.error('Invalid shutter specified (' + str(shutter) + ')')
            return -1

        status = self.status()
        timeout = 180.0
        elapsedTime = 0.0

        # if it's already open, return
        if status['Shutter' + str(shutter)] == 'OPEN':
            self.logger.info('Shutter ' + str(shutter) + ' already open')
            return

        # open the shutter
        start = datetime.datetime.utcnow()
        response = self.send('OPEN_SHUTTER_' + str(shutter))                
        self.logger.info(response)
        if not 'Success=TRUE' in response:
            # did the command fail?
            self.logger.warning('Failed to open shutter ' + str(shutter) + ': ' + response)
            ipdb.set_trace()
            # need to reset the PAC? ("Enclosure not in AUTO"?)
        
        # Wait for it to open
        self.logger.info('Waiting for shutter ' + str(shutter) + ' to open')
        status = self.status()
        while status['Shutter' + str(shutter)] == 'OPENING' and elapsedTime < timeout:
            status = self.status()
            elapsedTime = (datetime.datetime.utcnow()-start).total_seconds()

        # Did it fail to open?
        if status['Shutter' + str(shutter)] <> 'OPEN':
            self.logger.error('Error opening Shutter ' + str(shutter) )
            return -1

        self.logger.info('Shutter ' + str(shutter) + ' open')
            
    #close both shutter
    def close_both(self):
        timeout = 500
        elapsedTime = 0
        self.isOpen = False
        status = self.status()      
        if status['Shutter1'] == "CLOSED" and status['Shutter2'] == "CLOSED":
            self.logger.debug('Both shutters already closed')
            if self.mailsent:
                mail.send("Aqawan " + str(self.num) + " closed!","Love,\nMINERVA",level="critical")
                self.mailsent = False
        elif status['EnclOpMode'] == "MANUAL":
            self.logger.warning("Enclosure in manual; can't close")
            if self.mailsent:
                mail.send("Aqawan " + str(self.num) + " in manual","Please turn to 'AUTO' for computer control.\n Love,\nMINERVA")
                self.mailsent = False
        else:
            response = self.send('CLOSE_SEQUENTIAL')
            if not 'Success=TRUE' in response:
                self.logger.error('Aqawan failed to close!')
                self.isOpen = True
                if not self.mailsent:
                    mail.send("Aqawan " + str(self.num) + " failed to close!","Love,\nMINERVA",level="critical")
                    self.mailsent = True
                self.logger.info('Trying to close again!')
                self.close_both() # keep trying!
            else:
                self.logger.info(response)    
                start = datetime.datetime.utcnow()
                while (status['Shutter1'] <> "CLOSED" or status['Shutter2'] <> "CLOSED") and elapsedTime < timeout:
                    elapsedTime = (datetime.datetime.utcnow() - start).total_seconds()
                    status = self.status()
                if status['Shutter1'] <> "CLOSED" or status['Shutter2'] <> "CLOSED":
                    self.logger.error('Aqawan failed to close after ' + str(elapsedTime) + 'seconds!')
                    self.isOpen = True
                    if not self.mailsent:
                        mail.send("Aqawan " + str(self.num) + " failed to within the timeout!","Love,\nMINERVA",level="critical")
                        self.mailsent = True
                    self.close_both() # keep trying!
                else:
                    self.logger.info('Closed both shutters')
                    self.lastClose = datetime.datetime.utcnow()
                    if self.mailsent:
                        mail.send("Aqawan " + str(self.num) + " closed; crisis averted!","Love,\nMINERVA",level="critical")
                        self.mailsent = False
    
            
    # get aqawan status
    def status(self):
        response = self.send('STATUS').split(',')
        self.logger.debug("Status: " + str(response))
        status = {}
        for entry in response:
            if '=' in entry:
                status[(entry.split('='))[0].strip()] = (entry.split('='))[1].strip()

        # check to make sure it has everything we use
        requiredKeys = ['Shutter1', 'Shutter2', 'SWVersion', 'EnclHumidity',
                        'EntryDoor1', 'EntryDoor2', 'PanelDoor', 'Heartbeat',
                        'SystemUpTime', 'Fault', 'Error', 'PanelExhaustTemp',
                        'EnclTemp', 'EnclExhaustTemp', 'EnclIntakeTemp', 'LightsOn']
        
        for key in requiredKeys:
            if not key in status.keys():
                self.logger.error("Required key " + str(key) + " not present; trying again")
                status = self.status() # potential infinite loop!
                
        with open(self.currentStatusFile,'w') as outfile:
            json.dump(status,outfile)

        return status         

if __name__ == '__main__':

    aqawan_1 = aqawan(1)
    while True:
        command = raw_input('enter Aqawan command: ')
        print aqawan_1.send(command)
