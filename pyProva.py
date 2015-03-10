#!/usr/bin/python
import serial
import sys
import time
import argparse

class ProVa():
    def __init__(self,debug=False):
        self.ser = serial.Serial()
        self.ser.port = '/dev/ttyUSB0'
        self.ser.baudrate = 9600
        self.ser.timeout = 3
        self.ser.writeTimeout = 3
        self.result = ''
        self.readings = []
        self.channels = 2
        self.voltage = 0.0
        self.current = 0.0
        self.reading_valid = False
        self.debug = debug
        self.parse_valid = False

    def open(self):
        self.ser.open()
        return self.ser.isOpen()

    def close(self):
        self.ser.close()

    def get_port(self):
        return self.ser.port

    def read(self,channels=2):
        cmd = ' '
        try:
#           sys.stderr.write('cmd->\n')
            self.write(cmd)
        except serial.SerialTimeoutException:
            sys.stderr.write('write timeout\n')

        self.readings = []
        for chan in range(channels):
            self.result = self.ser.readline()
            if (len(self.result) > 0):
                self.readings.append(self.result.strip())

        rows = len(self.readings)
        if rows != channels:
             if self.debug:
                sys.stderr.write('Only got %d of %d channels. Received:\n' % (rows,channels) )
                for each in self.readings:
                    sys.stderr.write('   "%s"\n' % each )
        return rows

    def parse(self):
        self.parse_valid = True
        for each in self.readings:
            values = each.split()
            if len(values) >= 4:
                try:
                    if values[3] == 'V':
                        self.voltage = float(values[2])
                    if values[3] == 'A':
                        self.current = float(values[2])
                    if values[3] == 'mA':
                        self.current = float(values[2])/1000.0
                except:
                    self.parse_valid = False
            else:
                self.parse_valid = False

            if self.parse_valid == False:
                if self.debug:
                    sys.stderr.write('Bad parse of "%s"\n' % each)

        return self.parse_valid

    def write(self,data):
        self.ser.write(data)

    def do_reading(self,ch):
        self.reading_valid = False
        readings = self.read(channels=ch)
        if readings == ch:
            if self.parse():
                self.reading_valid = True

class Readings():
    def __init__(self):
        self.history = []
        self.wattage = 0.0
        self.wattseconds = 0.0
        self.last_readtime = 0.0
        self.last_wattseconds = 0.0

    def add_reading(self,readtime,voltage,current,first=False):
        if first:
            self.last_readtime = readtime

        self.wattage = voltage*current
        self.wattseconds = (readtime - self.last_readtime) * self.wattage
        self.last_readtime = readtime
        self.wattseconds = self.wattseconds + self.last_wattseconds
        self.last_wattseconds = self.wattseconds
        reading = dict(READTIME=readtime,VOLTAGE=voltage,CURRENT=current,WATTAGE=self.wattage,WATTSECONDS=self.wattseconds)
        self.history.append(reading)

    def get_last_reading(self):
        reading = self.history[len(self.history)]
        return reading

    def print_last_reading_csv(self):
        first = self.history[0]
        r = self.history[-1]
        print "%.1f, %.4f, %6.4f, %6.4f, %9.7f, %9.7f" % (r['READTIME'],(r['READTIME']-first['READTIME'])/3600,r['VOLTAGE'],r['CURRENT'],r['WATTAGE'],r['WATTSECONDS']/3600)
        sys.stdout.flush()

    def print_average_pwr(self):
        first = self.history[0]
        last  = self.history[-1]
        duration = last['READTIME']-first['READTIME']
        if (duration != 0.):
            pwr = last['WATTSECONDS']/duration
        else:
            pwr = 0

        print('\nAverage power: %9.7f W' % (pwr))
        sys.stdout.flush()

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Watt meter interface to the ProVa 903')
    parser.add_argument('-d','--delay', type=float, default=2, dest='delay',
                   help='Seconds per reading (default 2)')
    parser.add_argument('-c','--channels', type=int, default=2, dest='channels',
                   help='Expected channels per reading (default 2)')
#   parser.add_argument('-p','--port', type=int, default=2, dest='channels',
#                   help='Expected channels per reading (default 2)')
    parser.add_argument('-a','--avg',action='store_true',default=False,
                            help='Enable run average calculation')
    parser.add_argument('--debug', action='store_true', default=False,
                   help='Enable debug output')

    args = parser.parse_args()

    pv = ProVa(debug=args.debug)
    readings = Readings()

    def exit_program():
        pv.close()

    if not pv.open():
        print "open fail"
        sys.exit()

    sys.stderr.write('Opened %s\n' % pv.get_port() )

    try:
        # Need to do a special 1st read to init the time variable to Now.
        while True:
            pv.do_reading(args.channels)
            if pv.reading_valid:
                readings.add_reading(readtime=time.time(),voltage=pv.voltage,current=pv.current,first=True)
                readings.print_last_reading_csv()
                break;
            else:
                if not args.debug:
                    sys.stderr.write("Invalid Read")

        # Do a few quick readings at the start to sync to the start
        # This gives the user time to plug up/turn on the DUT.
        for i in range(5):
            pv.do_reading(args.channels)
            if pv.reading_valid:
                readings.add_reading(readtime=time.time(),voltage=pv.voltage,current=pv.current)
                readings.print_last_reading_csv()
    except KeyboardInterrupt:
        exit_program()

    time.sleep(1)

    # Start the endless reading loop.
    try:
        while True:
            this_read_time = time.time()
            pv.do_reading(args.channels)
            # Minumum loop so we don't spin
            default_loop_delay = 0.5
            if pv.reading_valid:
                readings.add_reading(readtime=this_read_time,voltage=pv.voltage,current=pv.current)
                readings.print_last_reading_csv()

            next_read_time = this_read_time + args.delay
            loop_delay = next_read_time - time.time()

            if pv.reading_valid:
                if loop_delay > 0:
                    time.sleep(loop_delay)
                else:
                    time.sleep(default_loop_delay)
            else:
                # if debug is on then there is plenty of output
                if not args.debug:
                    sys.stderr.write('%s: Bad reading\n' % this_read_time)
                time.sleep(default_loop_delay)

    except KeyboardInterrupt:
        pass

    if args.avg:
        readings.print_average_pwr()

    exit_program()

