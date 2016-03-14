from configobj import ConfigObj
import time, sys, socket, logging, datetime, ipdb, time, json, os, struct
import numpy as np
from scipy.interpolate import interp1d
import threading
import utils

class PT100:

    def __init__(self, config=None, base=None):

        self.config_file = config
        self.controller = config[-5]
	self.base_directory = base
	self.load_config()
	self.logger = utils.setup_logger(self.base_directory,self.night,self.logger_name)

    def load_config(self):
	
            try:
                    config = ConfigObj(self.base_directory + '/config/' + self.config_file)
            except:
                    print('ERROR accessing configuration file: ' + self.config_file)
                    sys.exit()
            self.ip = config['IP']
            self.port = int(config['PORT'])
            self.logger_name = config['LOGGER_NAME']
            self.description = config['DESCRIPTION']
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
            # reset the night at 10 am local                                                                                                 
            today = datetime.datetime.utcnow()
            if datetime.datetime.now().hour >= 10 and datetime.datetime.now().hour <= 16:
                    today = today + datetime.timedelta(days=1)
            self.night = 'n' + today.strftime('%Y%m%d')

    # interpolate the lookup table for a given resistance to derive the temp
    # https://www.picotech.com/download/manuals/USBPT104ProgrammersGuide.pdf
    def ohm2temp(self,ohm):
        reftemp = np.linspace(-50,200,num=251)
        refohm = np.loadtxt(self.base_directory+'/minerva_library/pt100.dat')
        f = interp1d(refohm,reftemp)#,kind='cubic)
        try: temp = f(ohm)[()]
        except: temp = None
        return temp

    def resistance(self,calib,m):
        if m[1] == m[0]: return 0.0
        resistance = calib*(m[3]-m[2])/(m[1]-m[0])/1000000.0
        return resistance

    def logtemp_robust(self):
        while True:
            try: self.logtemp()
            except: self.logger.exception("logtemp failed; retrying")
            try: self.sock.close()
            except: pass
            time.sleep(1.0)
            self.load_config()

    def logtemp(self):
        
        self.sock.settimeout(5.0)
        self.sock.gettimeout()

        self.logger.info("Sending data lock")

        self.sock.sendto("lock",(self.ip,self.port))
        val = self.sock.recv(2048)
        if 'Lock Success' not in val:
            self.logger.error("Error locking the data logger to this computer: " + val)
            return

        self.logger.info("Connecting to the data logger")
        self.sock.connect((self.ip,self.port))
        
        # Calibration data
        self.logger.info("Getting calibration data")
        self.sock.send("32".decode('hex'))
        val = self.sock.recv(2048)
        cal = struct.unpack_from('<8ciiii',val,offset=36)
        caldate = ''.join(cal[0:7])
        self.logger.info("Temperature sensors calibrated on " + caldate)
        caldata = cal[8:12]

        self.logger.info("Starting data collection")
        self.sock.send("31".decode('hex') + "ff".decode('hex'))
        val = self.sock.recv(2048)
        if "Converting" not in val:
            self.logger.error("Failed to begin data collection")
        time.sleep(1.0)

        ndx = {
            '\x00': 0,
            '\x04': 1,
            '\x08': 2,
            '\x0c': 3,
            }
            
        lastupdate= datetime.datetime.utcnow()
        verbose = False
        while True:
            try:

                # the logger hangs every once in a while; this is a hack solution to restart it...
                if (datetime.datetime.utcnow() - lastupdate).total_seconds() > 30:
                    self.logger.error("Logging slowed down for unknown reasons, restarting (hopefully)...")
                    self.sock.send("31".decode('hex') + "00".decode('hex'))
                    self.sock.close()
                    time.sleep(16.0) # wait for the connection to time out
                    return

                val = self.sock.recv(2048)

                if "Alive" in val:
                    pass
                elif "PT104" in val:
                    pass
                elif len(val) <> 20:
                    self.logger.error("Unexpected return string: " + val)
                else:

                    lastupdate = datetime.datetime.utcnow()

                    raw = struct.unpack('>cicicici',val)
                    meas = [float(raw[1]),float(raw[3]),float(raw[5]),float(raw[7])]

                    ohm = self.resistance(caldata[ndx[raw[0]]], meas)
                    temp = self.ohm2temp(ohm)

                    # log the temperature
                    night = 'n' + datetime.datetime.strftime(datetime.datetime.utcnow(),"%Y%m%d")
                    logdir = self.base_directory + '/log/' + night + '/' 
                    if not os.path.isdir(logdir):
                        os.mkdir(logdir)
                    filename = '%stemp.%s.%s.log'%(logdir,self.controller,str(ndx[raw[0]] + 1))
                    self.logger.info("Ohm=" + str(ohm) + ',temp=' + str(temp) + ',filename=' + filename + ',description='+self.description[ndx[raw[0]]])
                    with open(filename,'a') as f:    
                        f.write(datetime.datetime.strftime(datetime.datetime.utcnow(),'%Y-%m-%d %H:%M:%S.%f') + "," + str(temp)+ ',' + self.description[ndx[raw[0]]] + '\n')

                # keep it alive
                self.sock.send("34".decode('hex'))
                time.sleep(2.0)
            except:
                self.logger.exception("error logging controller %s"%(self.controller))
    
            
if __name__ == "__main__":

    configs = ['PT100A.ini','PT100B.ini','PT100C.ini','PT100D.ini']
    pt100s = []
    threads = []
    n=0
    if socket.gethostname() == 'Kiwispec-PC':
        base = 'C:/minerva-control/'
    else:
        base = '/home/minerva/minerva-control/'
    for config in configs:
        pt100s.append(PT100(config=config, base=base))
        threads.append(threading.Thread(target = pt100s[n].logtemp_robust))
        threads[n].start()
        n += 1

    ipdb.set_trace()
    
#    p1 = PT100(config="PT100_1.ini", base="C:/minerva-control/")
#    p2 = PT100(config="PT100_2.ini", base="C:/minerva-control/")
#    p3 = PT100(config="PT100_3.ini", base="C:/minerva-control/")
#    p4 = PT100(config="PT100_4.ini", base="C:/minerva-control/")
#    p3.logtemp()

    ipdb.set_trace()

    

    p3.sock.settimeout(5.0)
    p3.sock.gettimeout()

    p3.logger.info("Sending data lock")

    p3.sock.sendto("lock",(p3.ip,p3.port))
    val = p3.sock.recv(2048)
    if 'Lock Success' not in val:
        p3.logger.error("Error locking the data logger to this computer: " + val)

    p3.logger.info("Connecting to the data logger")
    p3.sock.connect((p3.ip,p3.port))
    
    # Calibration data
    p3.logger.info("Getting calibration data")
    p3.sock.send("32".decode('hex'))
    val = p3.sock.recv(2048)
    cal = struct.unpack_from('<8ciiii',val,offset=36)
    caldate = ''.join(cal[0:7])
    p3.logger.info("Temperature sensors calibrated on " + caldate)
    caldata = cal[8:12]

    p3.logger.info("Starting data collection")
    p3.sock.send("31".decode('hex') + "ff".decode('hex'))
    val = p3.sock.recv(2048)
    if val <> "Converting":
        p3.logger.error("Failed to begin data collection")
    time.sleep(1.0)

    ndx = {
        '\x00': 0,
        '\x04': 1,
        '\x08': 2,
        '\x0c': 3,
        }
        
    while True:
        try:
            val = p3.sock.recv(2048)
            raw = struct.unpack('>cicicici',val)
            meas = [float(raw[1]),float(raw[3]),float(raw[5]),float(raw[7])]

            ohm = p3.resistance(caldata[ndx[raw[0]]], meas)
            temp = p3.ohm2temp(ohm)
            print p3.description[ndx[raw[0]]], ohm, temp

#            # log the temperature
#            with open('temp' + str((self.num-1)*4 + ndx[raw[0]]]) + '.log','a') as f:
#                f.write(datetime.datetime.utcnow() + ',' + str(temp)+ ',' + self.description[ndx[raw[0]]])

            # keep it alive
            p3.sock.send("34".decode('hex'))
            time.sleep(0.1)
        except: pass
