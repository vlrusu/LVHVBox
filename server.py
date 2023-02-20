import socket
from threading import Thread
import queue
import time
import logging
import json
import serial
import os

from commands import *


BUFFER_SIZE = 20
HEADER_LENGTH=10


def process_command(command):

    func = getattr(lvhvbox,command.data["cmdname"])
    ret = func(command.data["args"])

    # This would be better as a real module, avoid global
    #ret = globals()[command[0]](command[1:])
    command.response = ret
    outgoing_queue.put(command)
    return 0

## ===========================================
## Store LV data in loop
## ===========================================

def lvloop(test):

    while (1):
        try:
            lvdata = lv_queue.get(block=False)
            retc = process_command(lvdata)

        except queue.Empty:
            lvhvbox.loglvdata()
            time.sleep(1)



## ===========================================
## Store HV data in loop
## ===========================================

# HV channels 0 to 5
# ==================
def hvloop0(test):

    while (1):
        try:
            hvdata = hv0_queue.get(block=False)
            retc = process_command(hvdata)

        except queue.Empty:
            lvhvbox.loghvdata0()
            time.sleep(1)


# HV channels 6 to 11
# ===================
def hvloop1(test):

    while (1):
        try:
            hvdata = hv1_queue.get(block=False)
            retc = process_command(hvdata)

        except queue.Empty:
            lvhvbox.loghvdata1()
            time.sleep(1)





class QueueTester(Thread):
    def __init__(self):
        Thread.__init__(self)

    def run(self):
        while True:
            command = lv_queue.get()
            logging.debug("Queueing data: " + command.data["cmdname"])
            time.sleep(3)
            command.response = "response"
            outgoing_queue.put(command)


class Command(object):
    def __init__(self, priority, data, conn):
        self.priority = priority
        self.data = data
        self.conn = conn
        self.response = ""

    def __gt__(self,other):
        return self.priority > other.priority

    def __lt__(self,other):
        return self.priority < other.priority

    def __eq__(self,other):
        return self.priority == other.priority


class CommandsThread(Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs=None, verbose=None):
        Thread.__init__(self)
        self.target = target
        self.name = name


    def run(self):
        while True:
#            if not commands_queue.empty():
                command = outgoing_queue.get()
                logging.debug("Finshed queue: " + command.data["cmdname"])

                data = {
                    "type": command.data["type"],
                    "cmdname": command.data["cmdname"],
                    "response": command.response
                    }
                serialized = json.dumps(data)
                msg = f"{len(serialized):<{HEADER_LENGTH}}"
                try:
                    command.conn.send(bytes(msg,"utf-8"))
                    command.conn.sendall(bytes(serialized,"utf-8"))
                except:
                    logging.debug("Connection send failed")



# Multithreaded Python server : TCP Server Socket Thread Pool
class ClientThread(Thread):
    def __init__(self, conn, ip, port):
        Thread.__init__(self)
        self.conn = conn
        self.ip = ip
        self.port = port
        print ("[+] New server socket thread started for " + ip + ":" + str(port))

    def run(self):
        while True:
            # Receive our "header" containing message length, it's size is defined and constant
            message_header = conn.recv(HEADER_LENGTH)

            # If we received no data, client gracefully closed a connection, for example using socket.close() or socket.shutdown(socket.SHUT_RDWR)
            if not len(message_header):
                print(f"Closed connection from {ip}:{port}")
                return

            # Convert header to int value
            message_length = int(message_header.decode('utf-8').strip())
            data = json.loads(conn.recv(message_length).decode('utf-8'))

            command  = Command(1, data, self.conn)
            print (f"Server received data: {data}")
            if not incoming_queue.full():
                if data["type"] == 0:
                    lv_queue.put(command)
                elif data["type"] == 1:
                    hv0_queue.put(command)
                elif data["type"] == 2:
                    hv1_queue.put(command)



## ==========================================================================================
## ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
##  MAIN FUNCTION
## ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
## ==========================================================================================

if __name__ == '__main__':
    is_test = True

    incoming_queue = queue.PriorityQueue(BUFFER_SIZE)
    lv_queue = queue.PriorityQueue(BUFFER_SIZE)
    hv0_queue = queue.PriorityQueue(BUFFER_SIZE)
    hv1_queue = queue.PriorityQueue(BUFFER_SIZE)
    outgoing_queue = queue.PriorityQueue(BUFFER_SIZE)


    # Multithreaded Python server : TCP Server Socket Program Stub
    TCP_IP = '127.0.0.1'
    TCP_PORT = 12000

    topdir = os.path.dirname(os.path.realpath(__file__))

    tcpServer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcpServer.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcpServer.bind((TCP_IP, TCP_PORT))
    threads = []

    c = CommandsThread(name='commands')
    c.start()
    threads.append(c)

    # q = QueueTester()
    # q.start()
    # threads.append(q)

    tcpServer.listen()
    print ("Multithreaded Python server : Waiting for connections from TCP clients...")


    logging.basicConfig(filename='lvhvbox.log', format='%(asctime)s:%(levelname)s:(%(threadName)-9s):%(message)s', encoding='utf-8', level=logging.DEBUG)


    # Decide which serial is 1 and which is 2
    if not is_test:
        sertmp1 = serial.Serial('/dev/ttyACM0', 115200, timeout=10,write_timeout = 1)
        sertmp2 = serial.Serial('/dev/ttyACM1', 115200, timeout=10,write_timeout = 1)

        sertmp1.timeout = None
        line = ""
        while(len(line)) < 30:
            line = sertmp1.readline().decode('ascii')
        whichone = line.split("|")[3][1]
        print("ser1 is " + str(whichone))

        if whichone == 1:
            ser1=sertmp1
            ser2=sertmp2
        else:
            ser1 = sertmp2
            ser2 = sertmp1

        sertmp2.timeout = None
        line = ""
        while(len(line)) < 30:
            line = sertmp2.readline().decode('ascii')
        whichone = line.split("|")[3][1]
        print("ser2 is " + str(whichone))


    # Log files
    lvlogname = "lvdata.log"
    lvlog = open(os.path.join(topdir,lvlogname),"w")
    hvlogname0 = "hvdata0.log"
    hvlog0 = open(os.path.join(topdir,hvlogname0),"w")
    hvlogname1 = "hvdata1.log"
    hvlog1 = open(os.path.join(topdir,hvlogname1),"w")


    if is_test:
        ser1=False
        ser2=False
    lvhvbox = LVHVBox(ser1,ser2,hvlog0, hvlog1,lvlog,is_test)


    lvThrd = threading.Thread(target=lvloop, args=[is_test], daemon = True, name="LVTHREAD")
    lvThrd.start()
    threads.append(lvThrd)
    hvThrd0 = threading.Thread(target=hvloop0, args=[is_test], daemon = True,  name="HV0THREAD")
    hvThrd0.start()
    threads.append(hvThrd0)
    hvThrd1 = threading.Thread(target=hvloop1, args=[is_test], daemon = True, name="HV1THREAD")
    hvThrd1.start()
    threads.append(hvThrd1)

while True:
    (conn, (ip, port)) = tcpServer.accept()
    print("accepted")
    newthread = ClientThread(conn, ip, port)
    newthread.start()
    threads.append(newthread)

for t in threads:
    t.join()
