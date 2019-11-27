from configobj import ConfigObj
from scp import SCPClient
from win32com.client import Dispatch
from scipy import stats
import numpy as np
import os,sys,glob, socket, logging, datetime, ipdb, time, json, threading, subprocess, collections
import atexit, win32api
import utils
import math
import ao
import zwo
import ascomcam, ascomfw
from astropy.io import fits

class server:

	def __init__(self, config, base=''):

		self.config_file = config
		self.base_directory = base
		self.load_config()

		# reset the night at 10 am local
		today = datetime.datetime.utcnow()
		if datetime.datetime.now().hour >= 10 and datetime.datetime.now().hour <= 16:
                        today = today + datetime.timedelta(days=1)
		night = 'n' + today.strftime('%Y%m%d')

		self.logger = utils.setup_logger(self.base_directory,self.night,self.logger_name)
		self.set_data_path()

                self.camera = ascomcam.ascomcam('',base=self.base_directory,driver='ASCOM.SDK2.Camera')
                self.guider = zwo.zwo('',self.base_directory)
                self.fw = ascomfw.ascomfw('',base=self.base_directory,driver='ASCOM.Apogee.FilterWheel')

		self.connect_camera()
		self.file_name = ''
		self.guider_file_name = ''

#		if socket.gethostname() == 't2-PC':
#			self.ao = ao.ao('ao_t' + socket.gethostname()[1] + '.ini')


#==============utility functions=================#
#these methods are not directly called by client

	def load_config(self):
		try:
			config = ConfigObj(self.base_directory+ '/config/' + self.config_file)
			self.host = config['HOST']
			self.port = int(config['PORT'])
			self.data_path_base = config['DATA_PATH']
			self.logger_name = config['LOGNAME']
			self.header_buffer = ''
		except:
			print('ERROR accessing configuration file: ' + self.config_file)
			sys.exit()


                today = datetime.datetime.utcnow()
                if datetime.datetime.now().hour >= 10 and datetime.datetime.now().hour <= 16:
                        today = today + datetime.timedelta(days=1)
                self.night = 'n' + today.strftime('%Y%m%d')

	def get_index(self,param):
		files = glob.glob(self.data_path + "/*.fits*")
		return 'success ' + str(len(files)+1)

	def get_status(self,param):

                try:
                        status = {}
                        status['CoolerOn'] = self.cam.CoolerOn
                        status['CurrentTemp'] = self.cam.Temperature
                        status['SetTemp'] = self.cam.TemperatureSetpoint
                        status['BinX'] = self.cam.BinX
                        status['BinY'] = self.cam.BinY
                        status['filter'] = self.cam.Filter
                        status['connected'] = self.cam.LinkEnabled
                        status['X1'] = self.cam.StartX
                        status['X2'] = self.cam.StartX + self.cam.NumX - 1
                        status['Y1'] = self.cam.StartY
                        status['Y2'] = self.cam.StartY + self.cam.NumY - 1
		except:
                        self.logger.exception("error getting camera status")
                        self.connect_camera()
                        return self.get_status(param)

		return 'success ' + json.dumps(status)

	#return true if temperature settles successfully, false if it fails
	def set_temperature(self,param,guider=False):

                if guider: camera = self.guider
                else: camera = self.camera

		try:
			setTemp = param.split()
			if len(setTemp) != 1:
				self.logger.error('parameter error')
				return 'fail'
			setTemp = float(setTemp[0])
			camera.cool(temp=setTemp)
			return 'success'
		except:
			self.logger.exception("Failed to set the temperature")
			return 'fail'

	def get_temperature(self, guider=False):
                if guider: camera = self.guider
                else: camera = self.camera
                
		try:
			return 'success '+ str(camera.get_temperature)
		except:
			return 'fail'

	def isAOPresent(self):
                if 'ao' in dir(self): return 'success'
                return 'fail'
        
#==========command functions==============#
#methods directly called by client

	def connect_camera(self):
        
                try:
                        self.camera.initialize()        
                        #self.guider.initialize()        
                        self.fw.initialize()
                        return 'sucess'
                except:
                        self.logger.exception("Failed to connect to the camera")
			return 'fail'

	#set binning
	def set_bin(self,param,guider=False):
                if guider: camera = self.guider
                else: camera = self.camera

		param = param.split()
		if len(param) != 2:
			return 'fail'
		try:
			self.logger.info('Setting binning to ' + param[0] + ',' + param[1] )
			camera.set_bin(int(param[0]),int(param[1]))
			return 'success'
		except:
			self.logger.error('Setting binning to ' + param[0] + ',' + param[1] + ' failed')
			return 'fail'

	def set_roi(self,param, guider=False):
                if guider: camera = self.guider
                else: camera = self.camera
                
		param = param.split()
		if len(param) != 4:
			return 'fail'
		try:
			# Set to full frame
			xsize = int(param[1])-int(param[0])+1
			ysize = int(param[3])-int(param[2])+1
			self.logger.info('Setting subframe to [' + param[0] + ':' + param[1] + ',' +
						 param[2] + ':' + param[3] + ']')
			if camera.set_roi(x1=param[0], x2=param[1], y1=param[2], y2=param[3]): return 'success'
			return 'fail'
		except:
			return 'fail'

	def get_filter_name(self,param):
		res = 'success '

		try:
			num = int(param)
			for i in range(int(param)):
				res += self.cam.FilterNames[i] + ' '
			return res
		except:
			return 'fail'

        def getGuideStar(self):
                time,x,y = self.guider.getGuideStar()
                timestr = time.strftime('%Y-%m-%dT%H:%M:%S.%f')
                return 'success ' + timestr + ' '+str(x)+' '+str(y)

	def expose(self,param, guider=False):
                if guider: camera=self.guider
                else: camera = self.camera
                
		try:
			param = param.split()
			exptime = float(param[0])
			openshutter = (param[1] == 1)
			filter_num = param[2]

			if filter_num != None:
                                self.fw.move_and_wait(position=int(filter_num))

			camera.expose(exptime,openshutter=openshutter)
			return 'success'
		except:
			return 'fail'

	def save_image(self,param, guider=False):
                if guider: camera=self.guider
                else: camera = self.camera

                try:
                        filename = self.data_path + param.split()[0]
                        camera.filename=filename
                        camera.save_image(filename)
                        return 'success'
                except:         
                        return 'fail'


	def write_header(self,param, guider=False):

                if guider: camera=self.guider
                else: camera=self.camera
		camera.header_buffer += param
		return 'success'

	def write_header_done(self,param, guider=False):
                if guider: camera=self.guider
                else: camera=self.camera
                
		try:
			filename=camera.filename
			self.logger.info("Writing header for " + filename)
		except:
			self.logger.error("file name not defined; saving failed earlier")
			camera.header_buffer = ''
			return 'fail'

		header_info = camera.header_buffer + param
		camera.header_buffer = ''

		try:
			# check to see if the image exists
			if os.path.isfile(filename):
                                f = fits.open(filename, 'update')
			else:
				self.logger.error("FITS file (" + filename + ") not found")
				return 'fail'

			try:
				hdr = json.loads(header_info,object_pairs_hook=collections.OrderedDict)
			except:
				self.logger.exception('Error updating header for ' + filename+ "; header string is: " + header_info)
				hdr = {}

			for key,value in hdr.iteritems():
				if isinstance(value, (str, unicode, float)):
					if isinstance(value,float):
						if math.isnan(value): value = 'NaN'
					f[0].header[key] = value
				else:
       					if isinstance(value[0],float):
               					if math.isnan(value[0]): value[0] = 'NaN'
                       			f[0].header[key] = (value[0],value[1])

			f.flush()
			f.close()
		except:
			self.logger.exception('Error updating header for ' + filename+ "; header string is: " + header_info)
			return 'fail'
		return 'success'

	def set_data_path(self):
		self.data_path = self.data_path_base + '\\' + self.night
		if not os.path.exists(self.data_path):
			os.makedirs(self.data_path)
		return 'success'

	def compress_data(self,night=None):
		try:
			#S This will throw if it doesn;t have data path, which
			#S seems like the only place how compression won't work now.
			#S Still need to practice caution though, as the thread that
			#S this function starts may still barf. I'm not sure if this should
			#S be communicated back to Main, but am still thinking about it.
			#TODO
			if night == None:
				data_path = self.data_path
			else:
				data_path = self.data_path_base+'\\'+night
			files = glob.glob(data_path + "/*.fits")
			compress_thread = threading.Thread(target = self.compress_thread,args = (files,))
			compress_thread.start()
			return 'success'

		except:
                        self.logger.exception('Compress thread failed to start')
			return 'fail'

	def compress_thread(self, files):
		for filename in files:
			logging.info('Compressing ' + filename)
			subprocess.call([self.base_directory + '/cfitsio/fpack.exe','-D',filename])


	def getMean(self,guider=False):
		try:
			if guider: mean = fits.getdata(self.file_name,0).mean()
			else: mean = fits.getdata(self.guider_file_name,0).mean()
			mean = str(mean)
			return 'success ' + mean
		except:
			return 'fail'

	def getMode(self,guider=False):
                
		try:
			if guider: image = fits.getdata(self.guider_file_name,0)
			else: image = fits.getdata(self.file_name,0)
			# mode is slow; take the central 100x100 region
			# (or the size of the image, which ever is smaller)
			nx = len(image)
			ny = len(image[1])
			size = 100
			x1 = int(max(nx/2.0 - size/2.0,0))
			x2 = int(min(nx/2.0 + size/2.0,nx-1))
			y1 = int(max(ny/2.0 - size/2.0,0))
			y2 = int(min(ny/2.0 + size/2.0,ny-1))

			mode = stats.mode(image[x1:x2,y1:y2],axis=None)[0][0]
			res = 'success ' + str(mode)
		except:
			res = 'fail'
                return res

	def isSuperSaturated(self, guider=False):
		try:
			if guider: image = pyfits.getdata(self.guider_file_name,0)
			else: image = pyfits.getdata(self.file_name,0)
			# mode is slow; take the central 100x100 region
			# (or the size of the image, which ever is smaller)
			nx = len(image)
			ny = len(image[1])
			size = 100
			x1 = max(nx/2.0 - size/2.0,0)
			x2 = min(nx/2.0 + size/2.0,nx-1)
			y1 = max(ny/2.0 - size/2.0,0)
			y2 = min(ny/2.0 + size/2.0,ny-1)

			photonNoise = 10.0 # made up, should do this better
			if np.std(image[x1:x2,y1:y2],axis=None) < photonNoise:
				return 'success true'
			else:
				return 'success false'
		except:
			return 'fail'

	def remove(self, guider=False):
		try:
			if guider: os.remove(self.guider_file_name)
			else: os.remove(self.file_name)
			return 'success'
		except:
			return 'fail'


	def disconnect_camera(self):
		try:
			self.logger.info('turning cooler off')
			self.cam.CoolerOn = False
			time.sleep(1)
			self.logger.info('disconnecting camera')
			self.cam.LinkEnabled = False
			return 'success'
		except:
                        self.logger.exception('disconnect failed')
			return 'fail'
#==================server functions===================#
#used to process communication between camera client and server==#

	#process received command from client program, and send response to given socket object
	def process_command(self, command, conn):
		tokens = command.split(None,1)
		if len(command) < 100:
			self.logger.info('command received: ' + command)
		if len(tokens) != 2:
			response = 'fail'
		elif tokens[0] == 'get_guide_star':
			response = self.getGuideStar()
		elif tokens[0] == 'get_filter_name':
			response = self.get_filter_name(tokens[1])
		elif tokens[0] == 'exposeGuider':
			response = self.exposeGuider(tokens[1])
		elif tokens[0] == 'expose':
			response = self.expose(tokens[1])
		elif tokens[0] == 'save_image':
			response = self.save_image(tokens[1])
		elif tokens[0] == 'set_camera_param':
			response = self.set_camera_param(tokens[1])
		elif tokens[0] == 'set_data_path':
			response = self.set_data_path()
		elif tokens[0] == 'get_status':
			response = self.get_status(tokens[1])
		elif tokens[0] == 'get_index':
			response = self.get_index(tokens[1])
		elif tokens[0] == 'set_binning':
			response = self.set_binning(tokens[1])
		elif tokens[0] == 'set_size':
			response = self.set_size(tokens[1])
		elif tokens[0] == 'write_header':
			response = self.write_header(tokens[1])
		elif tokens[0] == 'write_header_done':
			response = self.write_header_done(tokens[1])
		elif tokens[0] == 'compress_data':
			response = self.compress_data(night=tokens[1])
		elif tokens[0] == 'getMean':
			guider = (tokens[1] == 'guider')
			response = self.getMean(guider=guider)
		elif tokens[0] == 'getMode':
			guider = (tokens[1] == 'guider')
			response = self.getMode(guider=guider)
		elif tokens[0] == 'isSuperSaturated':
			guider = (tokens[1] == 'guider')
			response = self.isSuperSaturated(guider=guider)
                elif tokens[0] == 'isAOPresent':
                        response = self.isAOPresent() 
		elif tokens[0] == 'moveAO':
			array = tokens[1].split(',')
			response = self.ao.move(array[0],array[1])
		elif tokens[0] == 'homeAO':
			response = self.ao.home()
		elif tokens[0] == 'remove':
			guider = (tokens[1] == 'guider')
			response = self.remove(guider=guider)
		elif tokens[0] == 'connect_camera':
			response = self.connect_camera()
		elif tokens[0] == 'disconnect_camera':
			response = self.disconnect_camera()
		elif tokens[0] == 'set_temperature':
			response = self.set_temperature(tokens[1])
		elif tokens[0] == 'get_temperature':
			response = self.get_temperature()
		elif tokens[0] == 'quit_maxim':
			response = self.quit_maxim()
		else:
			self.logger.info('command not recognized: (' + tokens[0] +')')
			response = 'fail'
		try:
			conn.settimeout(3)
			conn.sendall(response)
			conn.close()
		except:
			self.logger.exception('failed to send response, connection lost')
			return

		if response.split()[0] == 'fail':
			self.logger.info('command failed: (' + tokens[0] +')')
		else:
			self.logger.info('command succeeded(' + tokens[0] +')')

	#server loop that handles incoming command
	def run_server(self):

		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try: s.bind((self.host, self.port))
		except:
			self.logger.exception("Error connecting to server")
			raise
		#s.listen(True)
                s.listen(4)

		while True:
			print 'listening to incoming connection on port ' + str(self.port)
			conn, addr = s.accept()
			try:
				conn.settimeout(3)
				data = conn.recv(1024)
			except:
				break
			if not data:break
			self.process_command(repr(data).strip("'"),conn)
		s.close()
		self.run_server()

if __name__ == '__main__':
    if socket.gethostname() == 'Minervared2-PC' or socket.gethostname() == 'Telcom-PC' or socket.gethostname() == 'minerva19-01':
        config_file = 'imager_server_red.ini'
    elif socket.gethostname() == "TacherControl":
        config_file = "imager_server_thach.ini"
    else:
	config_file = 'imager_server.ini'

    base_directory = 'C:\minerva-control'

    test_server = server(config_file,base_directory)
    test_server.run_server()
