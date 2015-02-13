from configobj import ConfigObj
from win32com.client import Dispatch
import logging, datetime, ipdb, time, json
# See http://www.cyanogen.com/help/maximdl/MaxIm-DL.htm#Scripting.htm

class imager:

    def __init__(self,camera_num, night, configfile=''):

        self.num = camera_num

        #set appropriate parameter based on aqawan_num
        #create configuration file object 
        configObj = ConfigObj(configfile)
        
        try:
            imagerconfig = configObj[self.num]
        except:
            print('ERROR accessing ', self.num, ".", 
                self.num, " was not found in the configuration file", configfile)
            return 

        self.platescale = float(imagerconfig['Setup']['PLATESCALE'])
        self.filters = imagerconfig['FILTERS']
        self.setTemp = float(imagerconfig['Setup']['SETTEMP'])
        self.maxcool = float(imagerconfig['Setup']['MAXCOOLING'])
        self.maxdiff = float(imagerconfig['Setup']['MAXTEMPERROR'])
        self.xbin = int(imagerconfig['Setup']['XBIN'])
        self.ybin = int(imagerconfig['Setup']['YBIN'])
        self.x1 = int(imagerconfig['Setup']['X1'])
        self.x2 = int(imagerconfig['Setup']['X2'])
        self.y1 = int(imagerconfig['Setup']['Y1'])
        self.y2 = int(imagerconfig['Setup']['Y2'])
        self.xcenter = int(imagerconfig['Setup']['XCENTER'])
        self.ycenter = int(imagerconfig['Setup']['YCENTER'])
        self.pointingModel = imagerconfig['Setup']['POINTINGMODEL']
        self.port = int(imagerconfig['Setup']['PORT'])
        self.datapath = ''
        self.gitpath = ''
        self.currentStatusFile = 'logs/current_' + self.num + '.log'
        
        logger_name = imagerconfig['Setup']['LOGNAME']
        log_file = 'logs/' + night + '/' + imagerconfig['Setup']['LOGFILE']
			
	# setting up aqawan logger
	self.logger = logging.getLogger(logger_name)
        formatter = logging.Formatter(fmt="%(asctime)s [%(filename)s:%(lineno)s - %(funcName)20s()] %(levelname)s: %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
	fileHandler = logging.FileHandler(log_file, mode='a')
	fileHandler.setFormatter(formatter)
	streamHandler = logging.StreamHandler()
	streamHandler.setFormatter(formatter)

	self.logger.setLevel(logging.DEBUG)
	self.logger.addHandler(fileHandler)
	self.logger.addHandler(streamHandler)

        self.cam = Dispatch("MaxIm.CCDCamera")

    def status(self):

        status = {}

        status['CoolerOn'] = self.cam.CoolerOn
        status['CurrentTemp'] = self.cam.Temperature
        status['SetTemp'] = self.cam.TemperatureSetpoint
        status['BinX'] = self.cam.BinX
        status['BinY'] = self.cam.BinY
        status['filter'] = self.filters[self.cam.Filter]
        status['connected'] = self.cam.LinkEnabled
        status['X1'] = self.cam.StartX
        status['X2'] = self.cam.StartX + self.cam.NumX - 1
        status['Y1'] = self.cam.StartY
        status['Y2'] = self.cam.StartY + self.cam.NumY - 1

        with open(self.currentStatusFile,'w') as outfile:
            json.dump(status,outfile)

        return status 

    def connect(self):
        settleTime = 900

        # Connect to an instance of Maxim's camera control.
        # (This launches the app if needed)
        self.logger.info('Connecting to Maxim') 
        self.cam = Dispatch("MaxIm.CCDCamera")

        # Connect to the camera 
        self.logger.info('Connecting to camera') 
        self.cam.LinkEnabled = True

        # Prevent the camera from disconnecting when we exit
        self.logger.info('Preventing the camera from disconnecting when we exit') 
        self.cam.DisableAutoShutdown = True

        # If we were responsible for launching Maxim, this prevents
        # Maxim from closing when our application exits
        self.logger.info('Preventing maxim from closing upon exit')
        maxim = Dispatch("MaxIm.Application")
        maxim.LockApp = True

        # Check that the filters match the Maxim config (can't set maxim config)
        for i in range(len(self.filters)):
#            ipdb.set_trace()
            if self.cam.FilterNames[i] not in self.filters.keys():
                self.logger.error('Configuration mismatch for filter ' + str(i) +
                                  '. Maxim filter = ' + self.cam.FilterNames[i])
            elif self.filters[self.cam.FilterNames[i]] <> str(i):
                self.logger.error('Configuration mismatch for filter ' + str(i) +
                                  '. Maxim filter = ' + self.cam.FilterNames[i] +
                                  '; config file filter = ' + self.filters[self.cam.FilterNames[i]])

        # Set binning
        self.logger.info('Setting binning to ' + str(self.xbin) + ',' + str(self.ybin) )
        self.cam.BinX = self.xbin
        self.cam.BinY = self.ybin

        # Set to full frame
        xsize = self.x2-self.x1+1
        ysize = self.y2-self.y1+1
        self.logger.info('Setting subframe to [' + str(self.x1) + ':' + str(self.x1 + xsize -1) + ',' +
                     str(self.y1) + ':' + str(self.y1 + ysize -1) + ']')

        self.cam.StartX = self.x1 #int((cam.CameraXSize/cam.BinX-CENTER_SUBFRAME_WIDTH)/2)
        self.cam.StartY = self.y1 #int((cam.CameraYSize/cam.BinY-CENTER_SUBFRAME_HEIGHT)/2)
        self.cam.NumX = xsize # CENTER_SUBFRAME_WIDTH
        self.cam.NumY = ysize # CENTER_SUBFRAME_HEIGHT

        self.logger.info('Turning cooler on')
        self.cam.TemperatureSetpoint = self.setTemp
        self.cam.CoolerOn = True
        start = datetime.datetime.utcnow()
        currentTemp = self.cam.Temperature
        elapsedTime = (datetime.datetime.utcnow() - start).total_seconds()

        # Wait for temperature to settle (timeout of 10 minutes)
        while elapsedTime < settleTime and (abs(self.setTemp - currentTemp) > self.maxdiff):    
            self.logger.info('Current temperature (' + str(currentTemp) +
                             ') not at setpoint (' + str(self.setTemp) +
                             '); waiting for CCD Temperature to stabilize (Elapsed time: '
                             + str(elapsedTime) + ' seconds)')
            time.sleep(10)
            currentTemp = self.cam.Temperature
            elapsedTime = (datetime.datetime.utcnow() - start).total_seconds()

        # Failed to reach setpoint
        if (abs(self.setTemp - currentTemp)) > self.maxdiff:
            self.logger.error('The camera was unable to reach its setpoint (' +
                              str(self.setTemp) + ') in the elapsed time (' +
                              str(elapsedTime) + ' seconds)')
      
