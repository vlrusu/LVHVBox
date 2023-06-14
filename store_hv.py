import serial


if __name__=='__main__':
    sertmp1 = serial.Serial('/dev/ttyACM0', 115200, timeout=15,write_timeout = 1)

    voltages = []
    currents = []

    write_file = open("channel_1.txt", "w")
    string_list = []


    
    for i in range(8000):
        temp_string = sertmp1.readline().decode('ascii')
        string_list.append(temp_string)

    
    for i in range(len(string_list)):
        write_file.write(str(i) + " " + string_list[i])

    write_file.close()


'''
    while True:
        print(sertmp1.readline().decode('ascii'))
'''