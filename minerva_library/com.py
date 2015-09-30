import serial
from configobj import ConfigObj
import logging, ipdb
import sys
import time, struct, datetime

class com:
    
    #S Initialization for com class. Lots of good stuff in here.
    def __init__(self, id, base, night, configfile='C:/minerva-control/config/com.ini'):
        #ipdb.set_trace()
        #S set the id of self to the memory addresss, unique identifier
        self.id = id
        self.base_directory = base
        
        #S Parses configfile into List based on id
        #? Not sure if this is how id is working, but makes sense. Need to look
        #? into *.ini files more. 
        configObj = ConfigObj(self.base_directory+configfile)

        #S Get the corresponding item/object (Typer??) from list of configObj,
        #S throws if not in configfile, printing to stdout. No log it 
        try:
            config = configObj[self.id]
        except:
            print('ERROR accessing ', self.id, ".", 
                self.id, " was not found in the configuration file", configfile)
            return
        
        #? Not really sure what is going on, need to look into com.ini
        self.flowcontrol = str(config['Setup']['FLOWCONTROL'])
        #self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        #S Looks like more fun in com.ini, I think it makes sense though, adds
        #S allowable serial commands for communication with instrument.
        self.allowedCmds = config['Setup']['ALLOWEDCMDS']

        #S Is this short for 'Termination String'? I think so, for ending a
        #S command in serila comm. A little confused as \n is CR and LF, may
        #S get into trouble with picky instruments.
        if config['Setup']['TERMSTR'] == r"\r":
            self.termstr = "\r"
        elif config['Setup']['TERMSTR'] == r"\r\n":
            self.termstr = "\r\n"
        elif config['Setup']['TERMSTR'] == r"\n\r":
            self.termstr = "\n\r"
        elif config['Setup']['TERMSTR'] == r"\n":
            self.termstr = "\n"
        elif config['Setup']['TERMSTR'] == "":
            self.termstr = ""

        #S Gives self a Serial class
        self.ser = serial.Serial()
        #S Get the port, baud, expected bits, and the stopbit from configfile.
        self.ser.port = str(config['Setup']['PORT'])
        self.ser.baudrate = int(config['Setup']['BAUDRATE'])
        self.ser.databits = int(config['Setup']['DATABITS'])
        #? Parity commented out?
#        self.ser.parity = str(config['Setup']['PARITY'])
        self.ser.stopbits = int(config['Setup']['STOPBITS'])

        #S Looks like log writing stuff, comes from configfile as well.
        logger_name = config['Setup']['LOGNAME']
        log_file = self.base_directory+'/log/' + night + '/' + config['Setup']['LOGFILE']
			
	# setting up logger
        fmt = "%(asctime)s [%(filename)s:%(lineno)s - %(funcName)s()] %(levelname)s: %(message)s"
        datefmt = "%Y-%m-%dT%H:%M:%S"

        #S Nead to read more into logging package, see what's going on here
        self.logger = logging.getLogger(logger_name)
        #S See above for formtas
        formatter = logging.Formatter(fmt,datefmt=datefmt)
        #S Read into logging.Formatter
        formatter.converter = time.gmtime

        #S Really just need to review logging. This is probably all good to go,
        #S but I'd like to see how it works. Could be useful later.
        fileHandler = logging.FileHandler(log_file, mode='a')
        fileHandler.setFormatter(formatter)

        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(logging.INFO)
        
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(fileHandler)
        self.logger.addHandler(console)

        #S Ensure that the serial port is definitely closed.
        self.ser.close()

    #S Opens serial comm port. Needs to be done if command is to be sent.
    #? When is appropriate to close? Upon termination of program, or completion
    #? of entire program? Limits on how many ports can be open? Also look into
    #? different ways of being able to handle open ports.
    def open(self):
        #S Opens serial comm port, will catch and log failure to open.
        #? Will this halt on error?
        try:
              self.ser.open()
        except serial.serialutil.SerialException as e:
            print e.errno, e.filename, e.strerror
            self.logger.error("Could not open serial port ({0}): {1}".format(e.errno, e.strerror))

    #S Closes serial comm port, see questions above.
    def close(self):
        self.ser.close()

    #S Functino for sending a command, makes sense. 
    def send(self,cmd):
        #? Checks to see if cmd is in self.allowedCmds? Not sure what that
        #? comment means. Need to check logic of True to confirm, my guess is
        #? it needs to be string matched some how.
        if True:#cmd in self.allowedCmds:
            #ipdb.set_trace()
            #S Opens serial comm
            self.open()
            
            if self.ser.isOpen():
                #S Sends command with termination string.
                self.ser.write(cmd + self.termstr)

                # let's wait one second before reading output (give device time to answer)
                time.sleep(1)
                #S Empty string for getting output. What happens is that
                #S self.ser.read(1) grabs the next byte in register, and clears that
                #S byte (I think, not sure on exact logistics yet). Anyways,
                #S ends up concatenating strings onto 'out' from read bytes.
                #S Returns out.
                out = ''

                #S .inWaiting condition checks to see if register is not empty.
                while self.ser.inWaiting() > 0:
                    byte = self.ser.read(1)
                    out = out + byte
                #S So we do have to close it after each command?
                #? Could we keep open somehow?
                self.close()
                return out
            #S If serial port couldn't open, should be caught earlier though?
            else:
                self.logger.error("Serial port not open")
        #S Doesn't actually chekc right now, I think it depends on if the
        #S allowable commands lists in com.ini are complete??
        else:
            self.logger.error("Command " + cmd + " not in allowed commands")
        self.close()


#S Looks like some testing code, will mess around with later though. 
if __name__ == "__main__":

#    specgauge = com('specgauge','n20150521')
#    print specgauge.send('RD')
#    ipdb.set_trace()

    expmeter = com('expmeter','n20150521')
    ipdb.set_trace()
    expmeter.send('R' + chr(1))
    expmeter.send('P' + chr(100))
    expmeter.send('D')

    measurementspersec = 2.0
    
    expmeter.send('P' + chr(int(100.0/measurementspersec)))

    expmeter.open()
    expmeter.ser.write('C' + expmeter.termstr)
    while True:
        try:
            while expmeter.ser.inWaiting() < 4:
                time.sleep(0.01)
            print str(datetime.datetime.utcnow()), struct.unpack('I',expmeter.ser.read(4))[0]
        except:  
            break
        
    expmeter.ser.write("\r") # stop measurements
    expmeter.ser.write('V'+ chr(0) + chr(0) + expmeter.termstr) # turn off voltage
    expmeter.close() # close connection
    ipdb.set_trace()
    
    com1 = CellHeater('COM3', 'n20150521', configfile = 'CellHeater.ini')
    com1.connect()
    ipdb.set_trace()
        
