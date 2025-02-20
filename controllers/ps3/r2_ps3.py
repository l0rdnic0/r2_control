#!/usr/bin/python
""" PS3 Joystick controller """
from __future__ import print_function
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import range
import pygame
import requests
import csv
import configparser
import os
import sys
import time
import datetime
import argparse
from io import StringIO
from collections import defaultdict
from SabertoothPacketSerial import SabertoothPacketSerial

import signal

def sig_handler(signal, frame):
    """ Handle signals """
    print('Cleaning Up')
    sys.exit(0)

signal.signal(signal.SIGINT, sig_handler)

##########################################################
# Load config
_configfile = 'ps3.cfg'
_config = configparser.SafeConfigParser({'log_file': '/home/pi/r2_control/logs/ps3.log',
                                         'baseurl' : 'http://localhost:5000/',
                                         'keepalive' : 0.25,
                                         'speed_fac' : 0.35,
                                         'invert' : -1,
                                         'accel_rate' : 0.025,
                                         'curve' : 0.6,
                                         'deadband' : 0.2})

_config.add_section('Dome')
_config.set('Dome', 'address', '129')
_config.set('Dome', 'type', 'Syren')
_config.set('Dome', 'port', '/dev/ttyUSB0')
_config.add_section('Drive')
_config.set('Drive', 'address', '128')
_config.set('Drive', 'type', 'Sabertooth')
_config.set('Drive', 'port', '/dev/ttyACM0')
_config.add_section('Axis')
_config.set('Axis', 'drive', '1')
_config.set('Axis', 'turn', '0')
_config.set('Axis', 'dome', '3')
_config.read(_configfile)

if not os.path.isfile(_configfile):
    print("Config file does not exist")
    with open(_configfile, 'wb') as configfile:
        _config.write(configfile)


mainconfig = _config.defaults()

##########################################################
# Set variables
# Log file location
log_file = mainconfig['log_file']

# How often should the script send a keepalive (s)
keepalive = float(mainconfig['keepalive'])

# Speed factor. This multiplier will define the max value to be sent to the drive system.
# eg. 0.5 means that the value of the joystick position will be halved
# Should never be greater than 1
speed_fac = float(mainconfig['speed_fac'])

# Invert. Does the drive need to be inverted. 1 = no, -1 = yes
invert = int(mainconfig['invert'])

drive_mod = speed_fac * invert

# Deadband: the amount of deadband on the sticks
deadband = float(mainconfig['deadband'])

# Exponential curve constant. Set this to 0 < curve < 1 to give difference response curves for axis
curve = float(mainconfig['curve'])

dome_speed = 0
accel_rate = float(mainconfig['accel_rate'])
dome_stick = 0

# Set Axis definitions
PS3_AXIS_LEFT_VERTICAL = int(_config.get('Axis', 'drive'))
PS3_AXIS_LEFT_HORIZONTAL = int(_config.get('Axis', 'turn'))
PS3_AXIS_RIGHT_HORIZONTAL = int(_config.get('Axis', 'dome'))

baseurl = mainconfig['baseurl']

os.environ["SDL_VIDEODRIVER"] = "dummy"

################################################################################
################################################################################
# Custom Functions
def locate(user_string="PS3 Controller", x=0, y=0):
    """ Place the text at a certain location """
    # Don't allow any user errors. Python's own error detection will check for
    # syntax and concatination, etc, etc, errors.
    x = int(x)
    y = int(y)
    if x >= 80: x = 80
    if y >= 40: y = 40
    if x <= 0: x = 0
    if y <= 0: y = 0
    HORIZ = str(x)
    VERT = str(y)
    # Plot the user_string at the starting at position HORIZ, VERT...
    print("\033["+VERT+";"+HORIZ+"f"+user_string)

def clamp(n, minn, maxn):
    """ Clamp a number between two values """
    if n < minn:
        if __debug__:
            print("Clamping min")
        return minn
    elif n > maxn:
        if __debug__:
            print("Clamping max " + str(n))
        return maxn
    else:
        return n

def shutdownR2():
    """ shutdownR2 - Put R2 into a safe state """
    if __debug__:
        print("Running shutdown procedure")
    if __debug__:
        print("Stopping all motion...")
        print("...Setting drive to 0")
    drive.driveCommand(0)
    if __debug__:
        print("...Setting turn to 0")
    drive.turnCommand(0)
    if __debug__:
        print("...Setting dome to 0")
    dome.driveCommand(0)

    if __debug__:
        print("Disable drives")
    url = baseurl + "servo/body/ENABLE_DRIVE/0/0"
    try:
        r = requests.get(url)
    except:
        print("Fail....")

    if __debug__:
        print("Disable dome")
    url = baseurl + "servo/body/ENABLE_DOME/0/0"
    try:
        r = requests.get(url)
    except:
        print("Fail....")

    if __debug__:
        print("Bad motivator")
    # Play a sound to alert about a problem
    url = baseurl + "audio/MOTIVATR"
    try:
        r = requests.get(url)
    except:
        print("Fail....")

    f.write(datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S') +
            " ****** PS3 Shutdown ******\n")

#######################################################

parser = argparse.ArgumentParser(description='PS3 controller for r2_control.')
parser.add_argument('--curses', '-c', action="store_true", dest="curses", required=False,
                    default=False, help='Output in a nice readable format')
parser.add_argument('--dryrun', '-d', action="store_true", dest="dryrun", required=False,
                    default=False, help='Output in a nice readable format')
args = parser.parse_args()

#### Open a log file
f = open(log_file, 'at')
f.write(datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S') +
        " : ****** ps3 started ******\n")
f.flush()

if not args.dryrun:
    if __debug__:
        print("Not a drytest")
    drive = SabertoothPacketSerial(address=int(_config.get('Drive', 'address')),
                                   type=_config.get('Drive', 'type'),
                                   port=_config.get('Drive', 'port'))
    dome = SabertoothPacketSerial(address=int(_config.get('Dome', 'address')),
                                  type=_config.get('Dome', 'type'),
                                  port=_config.get('Dome', 'port'))
    drive.driveCommand(0)
    drive.turnCommand(0)

pygame.display.init()

if args.curses:
    print('\033c')
    locate("-=[ PS3 Controller ]=-", 10, 0)
    locate("Left", 3, 2)
    locate("Right", 30, 2)
    locate("Joystick Input", 18, 3)
    locate("Drive Value (    )", 16, 7)
    locate('%4s' % speed_fac, 29, 7)
    locate("Last button", 3, 11)

while True:
    pygame.joystick.quit()
    pygame.joystick.init()
    num_joysticks = pygame.joystick.get_count()
    if __debug__:
        print("Waiting for joystick... (count: %s)" % num_joysticks)
    if num_joysticks != 0:
        f.write(datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S') +
                " : Joystick found \n")
        f.flush()
        break
    time.sleep(5)

pygame.init()
size = (pygame.display.Info().current_w, pygame.display.Info().current_h)
if __debug__:
    print("Framebuffer size: %d x %d" % (size[0], size[1]))

j = pygame.joystick.Joystick(0)
j.init()
buttons = j.get_numbuttons()

# Read in key combos from csv file
keys = defaultdict(list)
with open('keys.csv', mode='r') as infile:
    reader = csv.reader(infile)
    for row in reader:
        if __debug__:
            print("Row: %s | %s | %s" % (row[0], row[1], row[2]))
        keys[row[0]].append(row[1])
        keys[row[0]].append(row[2])

list(keys.items())

url = baseurl + "audio/Happy007"
try:
    r = requests.get(url)
except:
    if __debug__:
        print("Fail....")

f.write(datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S') +
        " : System Initialised \n")
f.flush()

last_command = time.time()
joystick = True

# Main loop
while (joystick):
    time.sleep(0.005)
    global previous
    #driveDome(dome_stick)
    difference = float(time.time() - last_command)
    if difference > keepalive:
        if __debug__:
            print("Last command sent greater than %s ago, doing keepAlive" % keepalive)
        #drive.keepAlive()
        #dome.keepAlive()
        # Check js0 still there
        if os.path.exists('/dev/input/js0'):
            if __debug__:
                print("Joystick still there....")
        else:
            print("No joystick")
            joystick = False
            shutdownR2()
        # Check for no shutdown file
        if os.path.exists('/home/pi/r2_control/controllers/.shutdown'):
            print("Shutdown file is there")
            joystick = False
            shutdownR2()
        last_command = time.time()
    try:
        events = pygame.event.get()
    except:
        if __debug__:
            print("Something went wrong!")
        shutdownR2()
        sys.exit(0)
    for event in events:
        if event.type == pygame.JOYBUTTONDOWN:
            buf = StringIO()
            for i in range(buttons):
                button = j.get_button(i)
                buf.write(str(button))
            combo = buf.getvalue()
            if __debug__:
                print("Buttons pressed: %s" % combo)
            if args.curses:
                locate("                   ", 1, 12)
                locate(combo, 3, 12)
            # Special key press (All 4 plus triangle) to increase speed of drive
            if combo == "00001111000000001":
                if __debug__:
                    print("Incrementing drive speed")
                # When detected, will increment the speed_fac by 0.5 and give some audio feedback.
                speed_fac += 0.05
                if speed_fac > 1:
                    speed_fac = 1
                if __debug__:
                    print("*** NEW SPEED %s" % speed_fac)
                if args.curses:
                    locate('%4f' % speed_fac, 28, 7)
                drive_mod = speed_fac * invert
                f.write(datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S') +
                        " : Speed Increase : " + str(speed_fac) + " \n")
                url = baseurl + "audio/Happy006"
                try:
                    r = requests.get(url)
                except:
                    if __debug__:
                        print("Fail....")
            # Special key press (All 4 plus X) to decrease speed of drive
            if combo == "00001111000000010":
                if __debug__:
                    print("Decrementing drive speed")
                # When detected, will increment the speed_fac by 0.5 and give some audio feedback.
                speed_fac -= 0.05
                if speed_fac < 0.2:
                    speed_fac = 0.2
                drive_mod = speed_fac * invert
                f.write(datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S') +
                        " : Speed Decrease : " + str(speed_fac) + " \n")
                url = baseurl + "audio/Sad__019"
                try:
                    r = requests.get(url)
                except:
                    if __debug__:
                        print("Fail....")
            try:
                newurl = baseurl + keys[combo][0]
                f.write(datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S') +
                        " : Button Down event : " + combo + "," + keys[combo][0] +" \n")
                f.flush()
                if __debug__:
                    print("Would run: %s" % keys[combo])
                    print("URL: %s" % newurl)
                try:
                    r = requests.get(newurl)
                except:
                    if __debug__:
                        print("No connection")
            except:
                if __debug__:
                    print("No combo (pressed)")
            previous = combo
        if event.type == pygame.JOYBUTTONUP:
            if __debug__:
                print("Buttons released: %s" % previous)
            try:
                newurl = baseurl + keys[previous][1]
                f.write(datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S') +
                        " : Button Up event : " + previous + "," + keys[previous][1] + "\n")
                f.flush()
                if __debug__:
                    print("Would run: %s" % keys[previous][1])
                    print("URL: %s" % newurl)
                try:
                    r = requests.get(newurl)
                except:
                    if __debug__:
                        print("No connection")
            except:
                if __debug__:
                    print("No combo (released)")
            previous = ""
        if event.type == pygame.JOYAXISMOTION:
            if event.axis == PS3_AXIS_LEFT_VERTICAL:
                if __debug__:
                    print("Value (Drive): %s : Speed Factor : %s" % (event.value, speed_fac))
                if args.curses:
                    locate("                   ", 10, 4)
                    locate('%10f' % (event.value), 10, 4)
                f.write(datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S') +
                        " : Forward/Back : " + str(event.value*drive_mod) + "\n")
                f.flush
                if not args.dryrun:
                    if __debug__:
                        print("Not a drytest")
                    drive.driveCommand(event.value*drive_mod)
                if args.curses:
                    locate("                   ", 10, 8)
                    locate('%10f' % (event.value*drive_mod), 10, 8)
                last_command = time.time()
            elif event.axis == PS3_AXIS_LEFT_HORIZONTAL:
                if __debug__:
                    print("Value (Steer): %s" % event.value)
                if args.curses:
                    locate("                   ", 10, 5)
                    locate('%10f' % (event.value), 10, 5)
                f.write(datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S') +
                        " : Left/Right : " + str(event.value*drive_mod) + "\n")
                f.flush
                if not args.dryrun:
                    if __debug__:
                        print("Not a drytest")
                    drive.turnCommand(event.value*drive_mod)
                if args.curses:
                    locate("                   ", 10, 9)
                    locate('%10f' % (event.value*drive_mod), 10, 9)
                last_command = time.time()
            elif event.axis == PS3_AXIS_RIGHT_HORIZONTAL:
                if __debug__:
                    print("Value (Dome): %s" % event.value)
                if args.curses:
                    locate("                   ", 35, 4)
                    locate('%10f' % (event.value), 35, 4)
                f.write(datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S') +
                        " : Dome : " + str(event.value) + "\n")
                f.flush
                if not args.dryrun:
                    if __debug__:
                        print("Not a drytest")
                    dome.driveCommand(clamp(event.value, -0.99, 0.99))
                if args.curses:
                    locate("                   ", 35, 8)
                    locate('%10f' % (event.value), 35, 8)
                last_command = time.time()
#                dome_stick = event.value

# If the while loop quits, make sure that the motors are reset.
if __debug__:
    print("Exited main loop")
shutdownR2()

