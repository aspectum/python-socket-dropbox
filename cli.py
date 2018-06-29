# Comentarios de funcoes analogas as do servidor em menos detalhe aqui
# Ver os comentarios do servidor

import socket
import pickle
import os
import re
import time

buffer_size = 4096      # Tamanho do buffer de recebimento do socket
segment_size = 2048     # Tamanho dos segmentos de arquivo a serem enviados/recebidos
currPath = ''           # Diretorio atual
usr = ''                # Nome de usuario
seq = 0                 # Numero de sequencia

comandos = {            # Dicionario com os cabecalhos correspondentes aos comandos e o numero de argumentos
    "ls": ('ls', 0),
    "cd": ('cd', 1),
    "mv": ('mv', 2),
    "rm": ('rm', 1),
    "mkdir": ('md', 1),
    "upload": ('ul', 2),
    "download": ('dl', 1),
    "ajuda": ('h', 0),
    "sair": ('q', 0)
}

# Monta e envia um pacote
def ssend(s, header, seq, currPath, data):
    seq += 1
    dataC = (header, [seq], [currPath], data)
    pktC = pickle.dumps(dataC)
    s.send(pktC)

# Recebe um pacote
def srecv(s):
    pktS = s.recv(buffer_size)
    dataS = pickle.loads(pktS)
    seq = dataS[1][0]
    currPath = dataS[2][0]
    return (seq, currPath, dataS)

# Realiza o arredondamento para cima (na hora de calcular o numero de pacotes para enviar um arquivo)
def ceil(n):
    res = int(n)
    return res if res == n or n < 0 else res+1

# Cria um diretorio
def mkdir(s, dirname):
    global seq, currPath
    try:
        os.makedirs(dirname)
        ssend(s, ['r', 'md'], seq, currPath, [])
        return 1
    except Exception as e:      # Ja existe pasta com o mesmo nome

        ssend(s, ['r', 'e'], seq, currPath, [e])
        print(e)
        return 0

# Faz as preparacoes para enviar um arquivo
def pre_enviaarq(s, nomearq, tmpdst):
    global seq, currPath
    try:    # Calcula o numero de pacotes necessario para enviar o arquivo
        tam = os.path.getsize(nomearq)
        numpkts = ceil(tam/segment_size)
    except Exception as e:
        print(e)
        return
    novonome = nomearq
    if '/' in nomearq:
        nomesplit = nomearq.split('/')
        novonome = nomesplit[-1]
    try:
        arq = open(nomearq, 'rb')
    except Exception as e:
        print(e)
        return
    # Envia ao servidor que sera feito o upload de um arquivo
    ssend(s, ['ul', 'aq'], seq, currPath, [novonome, tmpdst, numpkts])
    time.sleep(0.05)
    (seq, currPath, dataS) = srecv(s)
    # Checa se o arquivo abriu no servidor
    if dataS[0][0] == 'r':
        if dataS[0][1] == 'ul':
            pass
        elif dataS[0][1] == 'e':
            errormsg = dataS[3][0]
            print(errormsg)
            return
    enviaarq(s, arq)
    arq.close()

# Manda os segmentos do arquivo aberto em pre_enviaarq para o servidor
def enviaarq(s, arq):
    global seq, currPath
    seg = arq.read(segment_size)
    while seg:
        ssend(s, ['sd'], seq, currPath, [seg])
        (seq, currPath, dataS) = srecv(s)
        if dataS[0][0] == 'rv':
            pass
        seg = arq.read(segment_size)

# Faz as preparacoes para receber um arquivo
def pre_recebearq(s, nomearq, numpkts, dst):
    global seq, currPath
    novonome = nomearq
    if '/' in nomearq:  # Separa o nome do arquivo do diretorio completo
        nomesplit = nomearq.split('/')
        novonome = nomesplit[-1]
    if dst:
        novonome = dst + '/' + novonome
    try:
        arq = open(novonome, 'xb')
    except Exception as e:
        ssend(s, ['r', 'e'], seq, currPath, [e])
        time.sleep(0.05)
        print(e)
        return
    # Envia ao servidor que pode prosseguir com o download
    ssend(s, ['r', 'dl'], seq, currPath, [])
    time.sleep(0.05)
    recebearq(s, arq, numpkts)
    arq.close()

# Recebe os segmentos do servidor e os escreve no arquivo aberto em pre_recebearq
def recebearq(s, arq, numpkts):
    global seq, currPath
    i = 0
    while True:
        (seq, currPath, dataS) = srecv(s)
        seg = dataS[3][0]
        arq.write(seg)
        i = i+1

        ssend(s, ['rv'], seq, currPath, [])
        if i == numpkts:
            break

# Envia os arquivos e pastas de um diretorio
def enviaDir(s, diretorio, tmpdst):
    global seq, currPath
    dst = tmpdst + '/' + diretorio
    ssend(s, ['ul', 'dr'], seq, currPath, [dst])
    time.sleep(0.05)
    # Ve se criou a pasta base
    (seq, currPath, dataS) = srecv(s)
    if dataS[0][0] == 'r':
        if dataS[0][1] == 'md':
            pass
        elif dataS[0][1] == 'e':
            errormsg = dataS[3][0]
            print(errormsg)
            return
    for root, dirs, files in os.walk(diretorio):
        ssend(s, ['sd', 'aq'], seq, currPath, [])
        time.sleep(0.05)
        for nomearquivo in files:
            dst = tmpdst + '/' + root
            pre_enviaarq(s, root + '/' + nomearquivo, dst)
        ssend(s, ['sd', 'dr'], seq, currPath, [])
        time.sleep(0.05)
        for nomedir in dirs:
            diret = tmpdst + '/' + root + '/' + nomedir
            ssend(s, ['sd', 'dr'], seq, currPath, [diret])
            time.sleep(0.05)
            (seq, currPath, dataS) = srecv(s)
        ssend(s, ['sd', 'aq'], seq, currPath, [])
        time.sleep(0.05)
    ssend(s, ['r', 'ul'], seq, currPath, [])
    time.sleep(0.05)

# Recebe os arquivos e pastas de um diretorio
def recebeDir(s, nomedir):
    global seq, currPath
    if not mkdir(s, nomedir):
        return
    while 1:
        (seq, currPath, dataS) = srecv(s)
        if dataS[0][0] == 'sd':
            if dataS[0][1] == 'aq':
                pass
        elif dataS[0][0] == 'r':
            if dataS[0][1] == 'dl':
                break
        while 1:
            (seq, currPath, dataS) = srecv(s)
            if dataS[0][0] == 'r':
                if dataS[0][1] == 'dl':
                    pass
            elif dataS[0][0] == 'sd':
                if dataS[0][1] == 'dr':
                    break
            nomearq = dataS[3][0]
            numpkts = dataS[3][1]
            dst = dataS[3][2]
            pre_recebearq(s, nomearq, numpkts, dst)
        while 1:
            (seq, currPath, dataS) = srecv(s)
            if dataS[0][0] == 'sd':
                if dataS[0][1] == 'dr':
                    pass
                elif dataS[0][1] == 'aq':
                    break
            dirname = dataS[3][0]
            mkdir(s, dirname)

# Imprime para o cliente a ajuda, que consiste na lista e explicacao dos comandos e algumas observacoes
def ajuda():
    print("--------------------------------------COMANDOS--------------------------------------")
    print("ls ------------------------> lista arquivos e pastas no diretorio atual")
    print("cd caminho ----------------> navega para o diretorio 'caminho'")
    print("mkdir nome ----------------> cria uma pasta chamda 'nome' no diretorio atual")
    print("rm nome -------------------> remove o arquivo ou pasta chamado 'nome'")
    print("mv arquivo destino --------> move 'aqruivo' para 'destino'")
    print("upload arquivo destino ----> faz o upload de 'arquivo' para 'destino'")
    print("download arquivo ----------> faz o download de 'arquivo'")
    print("sair ----------------------> encerra o programa")
    print("-------------------------------------OBSERVACOES------------------------------------")
    print("* Caso o nome do arquivo ou pasta tenha espacos, coloca-lo entre aspas")
    print("* De modo geral pode-se usar '~' para referenciar o diretorio base atual")
    print("* O arquivo a ser feito upload deve estar no diretorio de execucao do cliente")
    print("* Do mesmo modo, o download e feito no diretorio de execucao do cliente")
    print("* Para mover de uma outra pasta deve usar '~'")
    print("* Para entrar no diretorio compartilhado use 'cd #shared' e para voltar 'cd #user'")
    print("* Enquanto o usuário estiver na pasta compartilhada, '~' se refere a ela")

# PedroBOX Protocol v2, ou PBP
# Recebe a entrada do cliente e gera o pacote de acordo com o protocolo
def PBP(s, entrada):
    global seq, currPath
    # Os 2 if's a seguir servem para caso o usuario queira passar algum argumento com espacos
    # tais como nome de arquivo ou pasta. Nesse caso ele deve usar aspas
    quotes = 0
    if '"' in entrada:
        quotes = 1
        elQuote = re.findall('"([^"]*)"', entrada)
        for el in elQuote:
            entrada = entrada.replace(el, "$$$")
    elementos = entrada.split(' ')
    i = 0
    if quotes:
        for n, el in enumerate(elementos):
            if el == '"$$$"':
                elementos[n] = elQuote[i]
                i = i+1
    comando = comandos.get(elementos[0], ('e', 0))
    # Numero de argumentos errado
    if comando[0] != 'e' and comando[1] != len(elementos)-1:
        print("Erro, numero de argumentos invalido")
        return
    # Uma serie de condicionais para os diversos comandos
    if comando[0] == 'ls':  # Comando de listar arquivos e pastas do diretorio
        # Envia o pacote
        ssend(s, ['ls'], seq, currPath, [])
        # Recebe o retorno
        (seq, currPath, dataS) = srecv(s)
        # O retorno e uma lista, que e mostrana na tela aqui
        dirlist = dataS[3]
        for nome in dirlist:
            print(nome)
        return
    elif comando[0] == 'cd':        # Mudar de diretorio
        diretorio = elementos[1]
        ssend(s, ['cd'], seq, currPath, [diretorio])
        (seq, currPath, dataS) = srecv(s)
        if dataS[0][0] == 'r':      # Checa o resultado
            if dataS[0][1] == 'cd':
                return
            elif dataS[0][1] == 'e':
                errormsg = dataS[3][0]
                print(errormsg)
                return
    elif comando[0] == 'mv':        # Mover arquivos
        filename = elementos[1]
        dst = elementos[2]
        ssend(s, ['mv'], seq, currPath, [filename, dst])
        (seq, currPath, dataS) = srecv(s)
        if dataS[0][0] == 'r':      # Checa o resultado
            if dataS[0][1] == 'mv':
                return
            elif dataS[0][1] == 'e':
                errormsg = dataS[3][0]
                print(errormsg)
                return
    elif comando[0] == 'rm':        # Remove arquivos ou pastas
        toBeDeleted = elementos[1]
        ssend(s, ['rm'], seq, currPath, [toBeDeleted])
        (seq, currPath, dataS) = srecv(s)
        if dataS[0][0] == 'r':      # Checa o resultado
            if dataS[0][1] == 'rm':
                return
            elif dataS[0][1] == 'e':
                errormsg = dataS[3][0]
                print(errormsg)
                return
    elif comando[0] == 'md':        # Cria uma pasta
        dirname = elementos[1]
        ssend(s, ['md'], seq, currPath, [dirname])
        (seq, currPath, dataS) = srecv(s)
        if dataS[0][0] == 'r':
            if dataS[0][1] == 'md':
                return
            elif dataS[0][1] == 'e':
                errormsg = dataS[3][0]
                print(errormsg)
                return
    elif comando[0] == 'ul':        # Comando de upload
        nomearq = elementos[1]
        tmpdst = elementos[2]
        if os.path.isdir(nomearq):  # Se e uma pasta
            enviaDir(s, nomearq, tmpdst)
        else:                       # Se e um arquivo
            pre_enviaarq(s, nomearq, tmpdst)
    elif comando[0] == 'dl':        # Comando de download
        nomearq = elementos[1]
        # Envia para o servidor
        ssend(s, ['dl'], seq, currPath, [nomearq])
        # Resposta do servidor
        (seq, currPath, dataS) = srecv(s)
        if dataS[0][0] == 'r':
            if dataS[0][1] == 'dl':
                if dataS[0][2] == 'aq':     # Se for um arquivo
                    numpkts = dataS[3][1]
                    dst = dataS[3][2]
                    pre_recebearq(s, nomearq, numpkts, dst)
                elif dataS[0][2] == 'dr':   # Se for uma pasta
                    nomedir = dataS[3][0]
                    recebeDir(s, nomedir)
                    pass
            elif dataS[0][1] == 'e':
                errormsg = dataS[3][0]
                print(errormsg)
                return
    elif comando[0] == 'h':     # Ajuda
        ajuda()
    elif comando[0] == 'q':     # Sair
        quit()
    elif comando[0] == 'e':     # Comando desconhecido
        print("Erro, comando " + elementos[0] + " inexistente")
        return

# Autenticacao do usuario
def signInCli(s):
    global seq, usr
    print("\n------AUTENTICACAO------")
    usr = input("Digite o username: ")
    psw = input("Digite a senha: ")
    # Envia o usuario e senha ao servidor
    ssend(s, ['si'], seq, [], [usr, psw])
    (seq, dataS) = srecv(s)[::2]
    if dataS[0][0] == 'r':      # Verifica a resposta do servidor
        if dataS[0][1] == 'si':
            print("Autenticacao realizada com sucesso.")
            return 1
        if dataS[0][1] == 'e':
            if dataS[0][2] == 'un':
                print("Erro, username nao cadastrado: " + usr)
                return 0
            elif dataS[0][2] == 'pn':
                print("Erro, senha errada")
                return 0

# Cadastro de usuario
def signUpCli(s):
    global seq, usr
    print("\n------CADASTRO------")
    usr = input("Digite um username: ")
    psw = input("Digite uma senha: ")
    # Envia ao servidor o usuario e senha
    ssend(s, ['su'], seq, [], [usr, psw])
    (seq, dataS) = srecv(s)[::2]
    if dataS[0][0] == 'r':      # Verifica a resposta do servidor
        if dataS[0][1] == 'su':
            print("Cadastro realizado com sucesso.")
            return 1
        if dataS[0][1] == 'e':
            if dataS[0][2] == 'ue':
                print(
                    "Nao foi possivel realizar o cadastro porque este username ja esta em uso: " + usr)
                return 0

# Login do cliente
def loginCli(s):
    global seq
    print("Bem vindo ao PedroBOX")
    print("Para continuar e necessario realizar a autenticacao")
    print("Menu de opcoes:")
    print("1 - Inserir credenciais")
    print("2 - Cadastrar novo usuario")
    print("0 - Sair")
    op = input("Opcao escolhida: ")
    # Teste de opcao valida
    while (op != '1') and (op != '2') and (op != '0'):
        print("\nOpcao invalida, escolha novamente")
        op = input("Opcao escolhida: ")
    # Chamando a funcao correspondente a opcao
    if op == '1':       # Inserir credenciais
        if not signInCli(s):
            s.close()
            quit()
    elif op == '2':     # Cadastro
        if not signUpCli(s):
            s.close()
            quit()
    else:               # Sair
        ssend(s, ['q'], seq, [], [])
        s.close()
        quit()

def Main():
    global seq, currPath, usr
    host = '127.0.0.1'
    port = 12345
    # Criacao do socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    loginCli(s)
    (seq, currPath, dataS) = srecv(s)
    if dataS[0][0] == 'p':
        svroot = dataS[3][0] + '/'
        msg = dataS[3][1]
        print(msg)
    tmpPath = currPath.replace(svroot, '')
    psPath = "PedroBOX:" + tmpPath + "> "
    while True:
        entrada = input('\n' + psPath)
        PBP(s, entrada)
        tmpPath = currPath.replace(svroot, '')
        psPath = "PedroBOX:" + tmpPath + "> "
    s.close()

if __name__ == '__main__':
    Main()