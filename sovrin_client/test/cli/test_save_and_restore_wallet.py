import os
from time import sleep

import pytest
from plenum.cli.cli import Exit, Cli
from plenum.common.util import createDirIfNotExists
from sovrin_client.client.wallet.wallet import Wallet
from sovrin_client.test.cli.helper import prompt_is, exitFromCli


def performExit(do):
    with pytest.raises(Exit):
        do('exit', within=3)


def testPersistentWalletName():

    # Connects to "test" environment
    walletFileName = Cli._normalizedWalletFileName("test")
    assert "test.wallet" == walletFileName
    assert "test" == Cli.getWalletKeyName(walletFileName)

    # New default wallet (keyring) gets created
    walletFileName = Cli._normalizedWalletFileName("Default")
    assert "default.wallet" == walletFileName
    assert "default" == Cli.getWalletKeyName(walletFileName)

    # User creates new wallet (keyring)
    walletFileName = Cli._normalizedWalletFileName("MyVault")
    assert "myvault.wallet" == walletFileName
    assert "myvault" == Cli.getWalletKeyName(walletFileName)


def checkWalletFilePersisted(filePath):
    assert os.path.exists(filePath)


def checkWalletRestored(cli, expectedWalletKeyName,
                       expectedIdentifiers):

    cli.lastCmdOutput == "Saved keyring {} restored".format(
        expectedWalletKeyName)
    assert cli._activeWallet.name == expectedWalletKeyName
    assert len(cli._activeWallet.identifiers) == \
           expectedIdentifiers


def getWalletFilePath(cli):
    fileName = cli.getPersistentWalletFileName()
    return Cli.getWalletFilePath(cli.getContextBasedKeyringsBaseDir(), fileName)


def getOldIdentifiersForActiveWallet(cli):
    oldIdentifiers = 0
    if cli._activeWallet:
        oldIdentifiers = len(cli._activeWallet.identifiers)
    return oldIdentifiers


def createNewKey(do, cli, keyringName):
    oldIdentifiers = getOldIdentifiersForActiveWallet(cli)
    do('new key', within=2,
       expect=["Key created in keyring {}".format(keyringName)])
    assert len(cli._activeWallet.identifiers) == oldIdentifiers + 1


def createNewKeyring(name, do, expectedMsgs=None):
    finalExpectedMsgs = expectedMsgs if expectedMsgs else [
           'Active keyring set to "{}"'.format(name),
           'New keyring {} created'.format(name)
        ]
    do(
        'new keyring {}'.format(name),
        expect=finalExpectedMsgs
    )


def useKeyring(name, do, expectedName=None, expectedMsgs=None):
    keyringName = expectedName or name
    finalExpectedMsgs = expectedMsgs or \
                        ['Active keyring set to "{}"'.format(keyringName)]
    do('use keyring {}'.format(name),
       expect=finalExpectedMsgs
    )


def _connectTo(envName, do, cli):
    do('connect {}'.format(envName), within=10,
       expect=["Connected to {}".format(envName)])
    prompt_is("{}@{}".format(cli.name, envName))


def connectTo(envName, do, cli, activeWalletPresents, identifiers,
              firstTimeConnect=False):
    currActiveWallet = cli._activeWallet
    _connectTo(envName, do, cli)
    if currActiveWallet is None and firstTimeConnect:
        do(None, expect=[
            "New keyring Default created",
            'Active keyring set to "Default"']
        )

    if activeWalletPresents:
        assert cli._activeWallet is not None
        assert len(cli._activeWallet.identifiers) == identifiers
    else:
        assert cli._activeWallet is None


def switchEnv(newEnvName, do, cli, checkIfWalletRestored=False,
              restoredWalletKeyName=None, restoredIdentifiers=0):
    walletFilePath = getWalletFilePath(cli)
    _connectTo(newEnvName, do, cli)

    # check wallet should have been persisted
    checkWalletFilePersisted(walletFilePath)

    if checkIfWalletRestored:
        checkWalletRestored(cli, restoredWalletKeyName, restoredIdentifiers)


def restartCli(cli, be, do, expectedRestoredWalletName,
               expectedIdentifiers):
    be(cli)
    _connectTo("pool1", do, cli)
    do(None, expect=[
        'Saved keyring "{}" restored'.format(expectedRestoredWalletName),
        'Active keyring set to "{}"'.format(expectedRestoredWalletName)
    ], within=5)
    assert cli._activeWallet is not None
    assert len(cli._activeWallet.identifiers) == expectedIdentifiers


def restartCliWithCorruptedWalletFile(cli, be, do, filePath):
    with open(filePath, "a") as myfile:
        myfile.write("appended text to corrupt wallet file")

    be(cli)
    _connectTo("pool1", do, cli)
    do(None,
       expect=[
           'error occurred while restoring wallet',
           'New keyring Default_',
           'Active keyring set to "Default_',
       ],
       not_expect=[
           'Saved keyring "Default" restored',
           'New keyring Default created',
           'Active keyring set to "Default"'
    ], within=5)


def testSaveAndRestoreWallet(do, be, cliForMultiNodePools,
                             aliceMultiNodePools,
                             earlMultiNodePools):
    be(cliForMultiNodePools)
    # No wallet should have been restored
    assert cliForMultiNodePools._activeWallet is None

    connectTo("pool1", do, cliForMultiNodePools,
              activeWalletPresents=True, identifiers=0, firstTimeConnect=True)
    createNewKey(do, cliForMultiNodePools, keyringName="Default")

    switchEnv("pool2", do, cliForMultiNodePools, checkIfWalletRestored=False)
    createNewKey(do, cliForMultiNodePools, keyringName="Default")
    createNewKeyring("mykr0", do)
    createNewKey(do, cliForMultiNodePools, keyringName="mykr0")
    createNewKey(do, cliForMultiNodePools, keyringName="mykr0")
    useKeyring("Default", do)
    createNewKey(do, cliForMultiNodePools, keyringName="Default")
    sleep(10)
    switchEnv("pool1", do, cliForMultiNodePools, checkIfWalletRestored=True,
              restoredWalletKeyName="Default", restoredIdentifiers=1)
    createNewKeyring("mykr1", do)
    createNewKey(do, cliForMultiNodePools, keyringName="mykr1")

    switchEnv("pool2", do, cliForMultiNodePools, checkIfWalletRestored=True,
              restoredWalletKeyName="Default", restoredIdentifiers=2)
    createNewKeyring("mykr0", do,
                     expectedMsgs = [
                         '"mykr0" conflicts with an existing keyring',
                         'Please choose a new name.'])

    filePath = Cli.getWalletFilePath(cliForMultiNodePools.getContextBasedKeyringsBaseDir(),
                                     cliForMultiNodePools.walletFileName)
    switchEnv("pool1", do, cliForMultiNodePools, checkIfWalletRestored=True,
              restoredWalletKeyName="mykr1", restoredIdentifiers=1)
    useKeyring(filePath, do, expectedName="mykr0",
               expectedMsgs=[
                   "Given wallet file ({}) doesn't "
                   "belong to current context.".format(filePath),
                   "Please connect to 'pool2' environment and try again."])

    # exit from current cli so that active wallet gets saved
    exitFromCli(do)

    # different tests for restoring saved wallet
    filePath = Cli.getWalletFilePath(cliForMultiNodePools.getContextBasedKeyringsBaseDir(),
                                     cliForMultiNodePools.walletFileName)
    restartCli(aliceMultiNodePools, be, do, "mykr1", 1)
    restartCliWithCorruptedWalletFile(earlMultiNodePools, be, do, filePath)


def testRestoreWalletFile(aliceCLI):
    import shutil
    fileName = "tmp_wallet_restore_issue"
    curPath = os.path.dirname(os.path.realpath(__file__))
    walletFilePath = os.path.join(curPath, fileName)
    keyringsDir = aliceCLI.getKeyringsBaseDir()
    createDirIfNotExists(keyringsDir)
    shutil.copy2(walletFilePath, keyringsDir)
    targetWalletFilePath = os.path.join(keyringsDir, fileName)
    wallet = aliceCLI.restoreWalletByPath(targetWalletFilePath)
    assert wallet is not None and isinstance(wallet, Wallet)
