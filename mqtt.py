#! /usr/bin/python3

import socket
import logging
import sys
import os
import traceback
import select
from sys import flags, stdin, version

PORT = 1883

def create_mqtt_connection_msg(id_mqtt):
    """
    Create a MQTT packet of type Connection with all flags to 0 excpt clean session.

    >>> create_mqtt_connection_msg("id 001").hex(" ")
    '10 12 00 04 4d 51 54 54 04 02 00 3c 00 06 69 64 20 30 30 31'
    """

    header = b'\x10'
    
    protocol_name = "MQTT".encode()
    id_mqtt = id_mqtt.encode()
    protocol_len = int.to_bytes(len(protocol_name), 2, 'big')
    
    version = int.to_bytes(4, 1, 'big')
    flags = b'\x02'
    keep_alive = int.to_bytes(60, 2, 'big')
    id_len = int.to_bytes(len(id_mqtt), 2, 'big')

    end_msg = protocol_len + protocol_name + version + flags + keep_alive + id_len + id_mqtt

    msg = header + int.to_bytes(len(end_msg), 1, 'big') + end_msg
    return msg

def check_conn_ack_msg(mqtt_msg):
    """
    Check validity of a conn ack msg
    >>> check_conn_ack_msg(bytes.fromhex("20020000"))
    True
    >>> check_conn_ack_msg(bytes.fromhex("20020001"))
    False
    
    #check_conn_ack_msg(bytes.fromhex("20040001")) plante car sys.ext(1)
    Error on conn ack paket (invalid lenght)
    """
    flags = mqtt_msg[0]
    msg_len = mqtt_msg[1]
    if (mqtt_msg[1] != 0):
        if (len(mqtt_msg[2:]) != msg_len):
            print("Error on conn ack paket (invalid lenght)")
            sys.exit(1)
        else:
            ret_code = mqtt_msg[-1]
            if ret_code == 0:
                return True
    return False

def decode_mqtt_publish_msg(mqtt_msg):
    """
    Extract topic and value from a mqtt publish message.

    >>> decode_mqtt_publish_msg(bytes.fromhex("300a000674656d7065723234"))
    ('temper', '24')
    >>> decode_mqtt_publish_msg(bytes.fromhex("300b000653616c6c6531616263"))
    ('Salle1', 'abc')
    >>> decode_mqtt_publish_msg(bytes.fromhex("310a000674656d7065723234"))
    ('temper', '24')
    >>> decode_mqtt_publish_msg(bytes.fromhex("310b000653616c6c6531616263"))
    ('Salle1', 'abc')
    """
    topic_len = mqtt_msg[2:4]
    topic_len = int.from_bytes(topic_len, 'big')
    topic = mqtt_msg[4:topic_len+4].decode()
    value = mqtt_msg[topic_len+4:len(mqtt_msg)].decode()
    return (topic,value)

def create_mqtt_subscriber_msg(topic):
    """
    Create a mqtt packet of type SUSCRIBE
    >>> create_mqtt_subscriber_msg("temper").hex(" ")
    '82 0b 00 01 00 06 74 65 6d 70 65 72 00'
    >>> create_mqtt_subscriber_msg("Salle1").hex(" ")
    '82 0b 00 01 00 06 53 61 6c 6c 65 31 00'
    >>> create_mqtt_subscriber_msg("554").hex(" ")
    '82 08 00 01 00 03 35 35 34 00'
    """

    header = b'\x82'
    msg_id = int.to_bytes(1, 2, 'big')
    topic = topic.encode()
    topic_len = len(topic).to_bytes(2, 'big')
    qos = b'\x00'
    msg = msg_id + topic_len + topic + qos
    msg = header + len(msg).to_bytes(1, 'big') + msg
    return msg

def decode_mqtt_subscriber_msg(msg):
    """
    decode topic from a mqtt suscriber massage
    """

    topic_len = msg[4:6]
    topic_len = int.from_bytes(topic_len, 'big')
    end_msg = topic_len + 6
    data = msg[6:end_msg]
    return data.decode()

def create_mqtt_publish_msg(topic, value, retain=False):
    """
    Creates a MQTT packet of type PUBLISH with DUP Flag=0 and QoS=0.

    >>> create_mqtt_publish_msg("temper", "24").hex(" ")
    '30 0a 00 06 74 65 6d 70 65 72 32 34'
    >>> create_mqtt_publish_msg("Salle1", "abc").hex(" ")
    '30 0b 00 06 53 61 6c 6c 65 31 61 62 63'
    >>> create_mqtt_publish_msg("temper", "24", True).hex(" ")
    '31 0a 00 06 74 65 6d 70 65 72 32 34'
    >>> create_mqtt_publish_msg("Salle1", "abc", True).hex(" ")
    '31 0b 00 06 53 61 6c 6c 65 31 61 62 63'
    """

    if retain:
        header = b'\x31'
    else:
        header = b'\x30'
    

    topic = topic.encode()
    value = value.encode()

    topic_lenght = int.to_bytes(len(topic), 2, 'big')

    msg_lenght = len(topic + value) + 2
    msg_lenght = int.to_bytes(msg_lenght, 1, 'big')

    msg = header + msg_lenght + topic_lenght + topic + value

    return msg


def run_publisher(addr, topic, pub_id, retain=False):
    """
    Run client publisher.
    """
    #connection au serveur
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)

    try:
        sock.connect(addr)
    except ConnectionRefusedError:
        print("Connection refused by server")
        sys.exit(1)
    except Exception as e:
        print("Error when connecting:", e)
        sys.exit(1)
    
    #envoie du packet de connection
    sock.sendall(create_mqtt_connection_msg(pub_id))

    #réception de la raiponse et vérification
    ack = sock.recv(1500)
    mqtt_msg = ack[-4:]
    if not check_conn_ack_msg(mqtt_msg):
        print("MQTT server refused connection")
    
    #envoie du msg publish
    print("Use ctrl+d for quit.")
    while True:
        try:
            value = input()
            sock.sendall(create_mqtt_publish_msg(topic, value, retain))
        except EOFError:
            break
        except KeyboardInterrupt:
            break
        except Exception as e:
            print("Error on read input:", e)
            break


    #on se déconnect du serveur.
    sock.sendall(b'\xe0\x00')
    sock.close
    print("bye")


def run_subscriber(addr, topic, sub_id):
    """
    Run client Suscriber
    """

    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)

    try:
        sock.connect(addr)
    except ConnectionRefusedError:
        print("Connection refused by server")
        sys.exit(1)
    except Exception as e:
        print("Error when connecting:", e)
        sys.exit(1)

    #envoie du packet de connection
    sock.sendall(create_mqtt_connection_msg(sub_id))

    #réception de la raiponse et vérification
    print("Send connection request...")
    ack = sock.recv(1500)
    mqtt_msg = ack[-4:]
    if not check_conn_ack_msg(mqtt_msg):
        print("MQTT server refused connection")
        sock.close()
        sys.exit(1)
    else:
        print("Connection established!")

    print("Send suscriber request...")
    sock.sendall(create_mqtt_subscriber_msg(topic))

    ack = sock.recv(1500)
    if ack[0] != 144:
        print("Failed to ack suscrib request")
        sys.exit(1)
    else:
        print("Suscribe ok")

    while True:
        try:
            data = sock.recv(1500)
            if data != b'':
                topic_d, value = decode_mqtt_publish_msg(data)
                print(topic_d, ": ", value)
        except KeyboardInterrupt:
            print("byebye")
            sock.sendall(b'\xe0\x00')
            sock.close()
            break



def run_server(addr):
    """
    Run main server loop
    """
    sc_dict = {}
    retain_dict = {}

    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM, 0)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    s.bind(addr)
    s.listen(1)
    l = []
    print("Setup complete")

    while True:
        r, _, _ = select.select(l + [s], [], [])
        for s2 in r:
  
            if s2== s:
                sclient, a = s.accept()
                print('Connexion entrante de', a)
                l = l + [sclient]

            else:
                data = s2.recv(1500)
                if data[0] == 16: #--> Connect
                    #print("Envoi connack ")
                    s2.sendall(b'\x20\x02\x00\x00')

                if data[0] == 48 or data[0] == 49: # --> publisher 
                    topic, val = decode_mqtt_publish_msg(data)
                    if topic in sc_dict:
                        for sclient in sc_dict[topic]:
                            msg = create_mqtt_publish_msg(topic, val)
                            sclient.sendall(msg)
                    if data[0] == 49:
                            retain_dict[topic] = val

                    #TODO: ajouter retain avec un autre dict
                    
                    
                    

                if data[0] == 130: #--> suscriber
                    topic = decode_mqtt_subscriber_msg(data)
                    if topic in sc_dict and sc_dict[topic] is not None:
                        sc_dict[topic] = sc_dict[topic].append(s2)
                    else:
                        sc_dict[topic] = [s2]

                    s2.sendall(b'\x90\x03\x00\x01\x00') # confimation de reception

                    if topic in retain_dict: # vérification d'un retain présent ou non
                        s2.send(create_mqtt_publish_msg(topic, retain_dict[topic]))


                if data[0] == 224: # déconexion
                    print('Déconnexion de', a)  
                    s2.close()
                    l.remove(s2)      
