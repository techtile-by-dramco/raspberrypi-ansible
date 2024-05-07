"""
0. start server "random_phases_ZMQ"
1. wait till random phase (step 2) or STOP (step 4) command of server
2. change phase randomnly and transmit for 'duration' seconds at next PPS
3. go to step 1.
4. stop

--ip "IP OF ZMQ SERVER"

Server port: 5558 topic: phase commands: start or stop


"""

import time
import argparse
import numpy as np
import uhd
#from uhd.usrp import dram_utils


def parse_args():
    """Parse the command line arguments"""
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--args", default="", type=str)
    parser.add_argument("-f", "--freq", type=float, required=True)
    parser.add_argument("-r", "--rate", default=1e6, type=float)
    parser.add_argument("-d", "--duration", default=1.0, type=float)
    parser.add_argument("-c", "--channels", default=0, nargs="+", type=int)
    parser.add_argument("-g", "--gain", type=float, default=10.0)
    parser.add_argument("--ip", required=True, type=str)
    return parser.parse_args()

import zmq

context = zmq.Context()
socket = context.socket(zmq.SUB)


def wait_till_go_from_server():
    """Wait till a message is received at ip:5557 for topic phase.

    Args:
        ip (str): IP Address of the server
    """
    
    # Receives a string format message
    topic = socket.recv_string()
    # todo check topic
    cmd = socket.recv_string()
    print(cmd)

    return cmd.lower()=="start"

def config_streamer(args, usrp):
    st_args = uhd.usrp.StreamArgs("fc32", "fc32")
    st_args.channels = args.channels
    return usrp.get_tx_stream(st_args)

def tx(usrp, duration, tx_streamer, rate, channels):
    metadata = uhd.types.TXMetadata()

    buffer_samps = tx_streamer.get_max_num_samps()
    samps_to_send = rate*duration

    random_phases = 0.5*np.exp(1j*np.random.rand(len(channels), 1)*2*np.pi)

    buffer = np.tile(random_phases, buffer_samps)

    send_samps = 0

    while send_samps < samps_to_send:
        samples = tx_streamer.send(0.7*np.ones((len(channels), buffer_samps), dtype=np.complex64), metadata)
        send_samps += samples
    # Send EOB to terminate Tx
    metadata.end_of_burst = True
    tx_streamer.send(np.zeros((len(channels), 1), dtype=np.complex64), metadata)
    # Help the garbage collection
    return send_samps

CLOCK_TIMEOUT = 1000  # 1000mS timeout for external clock locking

def setup_clock(usrp, clock_src, num_mboards):
    usrp.set_clock_source(clock_src)

    print("Now confirming lock on clock signals...")

    # Lock onto clock signals for all mboards
    for i in range(num_mboards):
        is_locked = usrp.get_mboard_sensor("ref_locked", i)
        while (not is_locked) and (datetime.now() < end_time):
            time.sleep(1e-3)
            is_locked = usrp.get_mboard_sensor("ref_locked", i)
        if not is_locked:
            print("Unable to confirm clock signal locked on board %d", i)
            return False
        else:
            print("Clock signals are locked")
    return True


def setup_pps(usrp, pps):
    """Setup the PPS source"""
    usrp.set_time_source(pps)
    return True
    
def multi_usrp_tx(args):
    """
    multi_usrp based TX example
    """
    usrp = uhd.usrp.MultiUSRP(args.args)
    setup_clock(usrp, "external", usrp.get_num_mboards())
    setup_pps(usrp, "external")

    for chan in args.channels:
        usrp.set_tx_rate(args.rate, chan)
        usrp.set_tx_freq(uhd.types.TuneRequest(args.freq), chan)
        usrp.set_tx_gain(args.gain, chan)


    while not usrp.get_rx_sensor("lo_locked").to_bool():
        time.sleep(0.01)

    print("RX LO is locked")

    while not usrp.get_tx_sensor("lo_locked").to_bool():
        time.sleep(0.01)

    print("TX LO is locked")
      
    tx_streamer = config_streamer(args, usrp)

    socket.connect(f"tcp://{args.ip}:{5558}")  # Connect to the publisher's address

    # Subscribe to topics
    socket.subscribe("phase")
    
    start = wait_till_go_from_server()
    while(start):
        tx(usrp, args.duration, tx_streamer, args.rate, args.channels)
        start = wait_till_go_from_server()

def main():
    """TX samples based on input arguments"""
    args = parse_args()
    if not isinstance(args.channels, list):
        args.channels = [args.channels]
    multi_usrp_tx(args)

if __name__ == "__main__":
    main()
