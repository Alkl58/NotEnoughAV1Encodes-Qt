#!/usr/bin/env python3
# This Python file uses the following encoding: utf-8

from PyQt5 import QtWidgets, uic, QtCore
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QFileDialog, QMessageBox
from multiprocessing.dummy import Pool
from functools import partial
from subprocess import call
from os import path
from pathlib import Path
from shutil import which
import os
import sys
import time
import subprocess
import asyncio
import platform
import psutil
import json
import math

import worker
import worker_splitting
import worker_scene
import worker_audio

class neav1e(QtWidgets.QMainWindow):

    videoInput = None
    videoOutput = None

    audio_encoding = False

    video_queue_first_pass = []
    video_queue_second_pass = []

    encoderSettings = None
    encoderOutput = None
    encoderOutputStats = None
    encoder_passes = None
    encoderPassOne = None
    encoderPassTwo = None
    pipeColorFMT = None
    filterCommand = None

    tempDir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".temp")
    tempDirFileName = None
    recommended_worker_count = None

    # FFmpeg expects ISO 639-2 codes for languages https://en.wikipedia.org/wiki/List_of_ISO_639-2_codes
    # ComboBoxes will be filled with this dictionary
    audioLanguageDictionary = {
        "English":      "eng", "Bosnian":       "bos", "Bulgarian":     "bul", "Chinese":       "chi",
        "Czech":        "cze", "Greek":         "gre", "Estonian":      "est", "Persian":       "per",
        "Filipino":     "fil", "Finnish":       "fin", "French":        "fre", "Georgian":      "geo",
        "German":       "ger", "Croatian":      "hrv", "Hungarian":     "hun", "Indonesian":    "ind",
        "Icelandic":    "ice", "Italian":       "ita", "Japanese":      "jpn", "Korean":        "kor",
        "Latin":        "lat", "Latvian":       "lav", "Lithuanian":    "lit", "Dutch":         "nld",
        "Norwegian":    "nob", "Polish":        "pol", "Portuguese":    "por", "Russian":       "rus",
        "Slovak":       "slk", "Slovenian":     "slv", "Spanish":       "spa", "Serbian":       "srp",
        "Swedish":      "swe", "Thai":          "tha", "Turkish":       "tur", "Ukrainian":     "ukr",
        "Vietnamese":   "vie"
        }

    def __init__(self):
        super(neav1e, self).__init__()
        pth = os.path.join(os.path.dirname(__file__), "form.ui")  # Set path ui
        uic.loadUi(pth, self)  # Load the .ui file
        self.setFixedWidth(842)  # Set Window Width
        self.setFixedHeight(568)  # Set Window Height
        self.setWindowTitle("NotEnoughAV1Encodes-Qt")  # Set Window Title

        # Controls IO
        self.pushButtonOpenSource.clicked.connect(self.openVideoSource)
        self.pushButtonSaveTo.clicked.connect(self.setVideoDestination)

        # Controls Start / Stop
        self.pushButtonStart.clicked.connect(self.mainEntry)
        # self.pushButtonCancel.clicked.connect(self.encode_audio)

        # Controls Splitting
        self.comboBoxSplittingMethod.currentIndexChanged.connect(self.splittingUI)
        self.checkBoxSplittingReencode.stateChanged.connect(self.splittingReencode)

        self.horizontalSliderQ.valueChanged.connect(self.setQSliderValue)
        self.horizontalSliderEncoderSpeed.valueChanged.connect(self.setSpeedSliderValue)
        self.comboBoxSplittingMethod.currentIndexChanged.connect(self.setSummarySplitting)

        # Controls Encoder
        self.comboBoxEncoder.currentIndexChanged.connect(self.setEncoderUI)
        self.comboBoxPasses.currentIndexChanged.connect(self.setEncoderPassRav1e)
        self.radioButtonVBR.toggled.connect(self.toggleVBRQ)
        self.checkBoxAdvancedSettings.stateChanged.connect(self.toggleAdvancedSettings)
        self.checkBoxAomencDenoise.stateChanged.connect(self.toggleAomencDenoise)
        self.checkBoxRav1eContentLight.stateChanged.connect(self.toggleRav1eContentLight)

        # Custom Settings
        self.groupBoxCustomSettings.toggled.connect(self.toggleCustomSettings)

        # !!! CHANGE IN UI FILE !!!
        self.labelSplittingChunkLength.hide()
        self.spinBoxChunking.hide()
        self.checkBoxSplittingReencode.hide()
        self.comboBoxSplittingReencode.hide()
        self.groupBoxAom.show()
        self.groupBoxRav1e.hide()
        self.groupBoxSvtav1.hide()

        self.tabWidget.setTabEnabled(4, False)

        # Set Worker Count ComobBox
        for i in range(1, psutil.cpu_count(logical = False) + 1):
            self.comboBoxWorkerCount.addItem(str(i))
        self.comboBoxWorkerCount.setCurrentIndex(int((psutil.cpu_count(logical = False) - 1) * 0.75))
        self.recommended_worker_count = int((psutil.cpu_count(logical = False) - 1) * 0.75)

        self.fillAudioLanguage()

        # Check if FFmpeg is in Path
        if which("ffmpeg") is None:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText("FFmpeg not found in PATH!")
            msg.setWindowTitle("Error")
            msg.exec()
            # Exit Program
            sys.exit()

        # Show the GUI
        self.show()

    #  ═════════════════════════════════════════ Audio ════════════════════════════════════════

    def encode_audio(self):
        command = ""
        if self.groupBoxTrackOne.isChecked():
            command += self.audioCMDGenerator("0", self.comboBoxTrackOneCodec.currentText(), str(self.spinBoxTrackOneBitrate.value()), self.switchAudioChannelLayout(str(self.comboBoxTrackOneLayout.currentIndex())), self.switchAudioLanguage(self.comboBoxTrackOneLanguage.currentText()))
        if self.groupBoxTrackTwo.isChecked():
            command += self.audioCMDGenerator("1", self.comboBoxTrackTwoCodec.currentText(), str(self.spinBoxTrackTwoBitrate.value()), self.switchAudioChannelLayout(str(self.comboBoxTrackTwoLayout.currentIndex())), self.switchAudioLanguage(self.comboBoxTrackTwoLanguage.currentText()))
        if self.groupBoxTrackThree.isChecked():
            command += self.audioCMDGenerator("2", self.comboBoxTrackThreeCodec.currentText(), str(self.spinBoxTrackThreeBitrate.value()), self.switchAudioChannelLayout(str(self.comboBoxTrackThreeLayout.currentIndex())), self.switchAudioLanguage(self.comboBoxTrackThreeLanguage.currentText()))
        if self.groupBoxTrackThree.isChecked():
            command += self.audioCMDGenerator("3", self.comboBoxTrackFourCodec.currentText(), str(self.spinBoxTrackFourBitrate.value()), self.switchAudioChannelLayout(str(self.comboBoxTrackFourLayout.currentIndex())), self.switchAudioLanguage(self.comboBoxTrackFourLanguage.currentText()))
        command += " -af aformat=channel_layouts=" + '\u0022' + "7.1|5.1|stereo|mono" + '\u0022'

        if self.groupBoxTrackOne.isChecked() or self.groupBoxTrackTwo.isChecked() or self.groupBoxTrackThree.isChecked() or self.groupBoxTrackThree.isChecked():
            out_path = Path(os.path.join(self.tempDir, self.tempDirFileName, "Audio"))
            out_path.mkdir(parents=True, exist_ok=True)
            audio_output = os.path.join(self.tempDir, self.tempDirFileName, "Audio", "audio.mkv")
            self.audio_encoding = True
            # Create a QThread object
            self.thread_encode_audio = QThread()
            # Create a worker object
            self.worker_encode_audio = worker_audio.WorkerAudio()
            # Move worker to the thread
            self.worker_encode_audio.moveToThread(self.thread_encode_audio)
            # Connect signals and slots
            self.thread_encode_audio.started.connect(partial(self.worker_encode_audio.run, self.videoInput, command, audio_output))
            self.worker_encode_audio.finished.connect(self.thread_encode_audio.quit)
            self.worker_encode_audio.finished.connect(self.splitting)
            self.worker_encode_audio.finished.connect(self.worker_encode_audio.deleteLater)
            self.thread_encode_audio.finished.connect(self.thread_encode_audio.deleteLater)
            # Start the thread
            self.thread_encode_audio.start()
        else:
            self.audio_encoding = False
            self.splitting()

    def audioCMDGenerator(self, activetrackindex, audioCodec, activetrackbitrate, channellayout, lang):
        # Audio Mapping
        audio = '-map 0:a:' + activetrackindex + ' -c:a:' + activetrackindex
        # Codec
        audio += self.switchAudioCodec(audioCodec)
        # Channel Layout / Bitrate
        audio += ' -b:a:' + activetrackindex + ' ' + activetrackbitrate + 'k'
        audio += ' -ac:a:' + activetrackindex + ' ' + channellayout
        # Metadata
        audio += ' -metadata:s:a:' + activetrackindex + ' language=' + lang
        audio += ' -metadata:s:a:' + activetrackindex + ' title=' + '\u0022' + '[' + lang.upper() + '] ' + audioCodec + ' ' + activetrackbitrate + 'kbps' + '\u0022'
        return audio

    def switchAudioLanguage(self, lang):
        return self.audioLanguageDictionary[lang]

    def switchAudioCodec(self, codec):
        value = ""
        if codec == "Opus":
            value = ' libopus'
        elif codec == "AC3":
            value = ' ac3'
        elif codec == "AAC":
            value = ' aac'
        elif codec == "MP3":
            value = ' libmp3lame'
        return value

    def switchAudioChannelLayout(self, layout):
        value = ""
        if layout == "0":
            value = '1'
        elif layout == "1":
            value = '2'
        elif layout == "3":
            value = '6'
        elif layout == "4":
            value = '8'
        return value

    def ffprobeAudioDetect(self):
        cmd="ffprobe -i " + '\u0022' + self.videoInput + '\u0022' + "  -loglevel error -select_streams a -show_entries stream=index -of csv=p=1"
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,universal_newlines=True, shell=True)

        temp = []
        for line in process.stdout:
            temp.append(line)
        joined = ''.join(temp).split()
        
        counter = 0
        trackOne = trackTwo = trackThree = trackFour = False
        for _ in joined:
            if counter == 0:
                trackOne = True
            if counter == 1:
                trackTwo = True
            if counter == 2:
                trackThree = True
            if counter == 3:
                trackFour = True
            counter += 1

        self.groupBoxTrackOne.setEnabled(trackOne)
        self.groupBoxTrackOne.setChecked(trackOne)
        self.groupBoxTrackTwo.setEnabled(trackTwo)
        self.groupBoxTrackTwo.setChecked(trackTwo)
        self.groupBoxTrackThree.setEnabled(trackThree)
        self.groupBoxTrackThree.setChecked(trackThree)
        self.groupBoxTrackFour.setEnabled(trackFour)
        self.groupBoxTrackFour.setChecked(trackFour)

    #  ═══════════════════════════════════════ UI Logic ═══════════════════════════════════════

    def fillAudioLanguage(self):
        # Clears Audio Language ComboBox & fills it with the dictionary
        self.comboBoxTrackOneLanguage.clear()
        self.comboBoxTrackTwoLanguage.clear()
        self.comboBoxTrackThreeLanguage.clear()
        self.comboBoxTrackFourLanguage.clear()
        for i in self.audioLanguageDictionary:
            self.comboBoxTrackOneLanguage.addItem(i)
            self.comboBoxTrackTwoLanguage.addItem(i)
            self.comboBoxTrackThreeLanguage.addItem(i)
            self.comboBoxTrackFourLanguage.addItem(i)
        
    def toggleCustomSettings(self):
        if self.groupBoxCustomSettings.isChecked():
            self.groupBoxAom.setEnabled(False)
            self.groupBoxRav1e.setEnabled(False)
            self.groupBoxSvtav1.setEnabled(False)
            self.setEncoderSettings()
            self.textEditCustomSettings.setPlainText(self.encoderSettings)
        else:
            self.groupBoxAom.setEnabled(True)
            self.groupBoxRav1e.setEnabled(True)
            self.groupBoxSvtav1.setEnabled(True)

    def toggleRav1eContentLight(self):
        self.spinBoxRav1eCll.setEnabled(self.checkBoxRav1eContentLight.isChecked() is True)
        self.spinBoxRav1eFall.setEnabled(self.checkBoxRav1eContentLight.isChecked() is True)

    def toggleAomencDenoise(self):
        self.spinBoxAomencDenoise.setEnabled(self.checkBoxAomencDenoise.isChecked() is True)

    def toggleAdvancedSettings(self):
        self.tabWidget.setTabEnabled(4, self.checkBoxAdvancedSettings.isChecked() is True)

    def toggleVBRQ(self, a):
        if a:
            self.horizontalSliderQ.setEnabled(False)
            self.spinBoxVBR.setEnabled(True)
        else:
            self.horizontalSliderQ.setEnabled(True)
            self.spinBoxVBR.setEnabled(False)

    def setEncoderPassRav1e(self, n):
        if n == 1 and self.comboBoxEncoder.currentIndex() == 1:
            self.comboBoxPasses.setCurrentIndex(0) # rav1e two pass still broken
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("rav1e currently does not support 2pass encoding.")
            msg.setWindowTitle("Attention!")
            msg.exec()

    def setEncoderUI(self, n):
        if n == 0:
            #aomenc
            self.horizontalSliderEncoderSpeed.setMaximum(9)
            self.horizontalSliderEncoderSpeed.setValue(5)
            self.horizontalSliderQ.setMaximum(63)
            self.horizontalSliderQ.setValue(28)
            self.comboBoxWorkerCount.setCurrentIndex(self.recommended_worker_count)
            self.groupBoxAom.show()
            self.groupBoxRav1e.hide()
            self.groupBoxSvtav1.hide()
        elif n == 1:
            #rav1e
            self.horizontalSliderEncoderSpeed.setMaximum(10)
            self.horizontalSliderEncoderSpeed.setValue(6)
            self.horizontalSliderQ.setMaximum(255)
            self.horizontalSliderQ.setValue(100)
            self.comboBoxWorkerCount.setCurrentIndex(self.recommended_worker_count)
            self.comboBoxPasses.setCurrentIndex(0) # rav1e two pass still broken
            self.groupBoxAom.hide()
            self.groupBoxRav1e.show()
            self.groupBoxSvtav1.hide()
        elif n == 2:
            #svt-av1
            self.horizontalSliderQ.setMaximum(63)
            self.horizontalSliderQ.setValue(28)
            self.horizontalSliderEncoderSpeed.setMaximum(8)
            self.horizontalSliderEncoderSpeed.setValue(5)
            self.comboBoxWorkerCount.setCurrentIndex(0)
            self.groupBoxAom.hide()
            self.groupBoxRav1e.hide()
            self.groupBoxSvtav1.show()

    def setSummarySplitting(self):
        self.labelSummarySplitting.setText(str(self.comboBoxSplittingMethod.currentText()))

    def reportProgress(self, n):
        self.progressBar.setValue(n)

    def setQSliderValue(self):
        self.labelQ.setText(str(self.horizontalSliderQ.value()))

    def setSpeedSliderValue(self):
        self.labelSpeed.setText(str(self.horizontalSliderEncoderSpeed.value()))

    def splittingReencode(self):
        if self.checkBoxSplittingReencode.isChecked() is True:
            self.comboBoxSplittingReencode.setEnabled(True)
        else:
            self.comboBoxSplittingReencode.setEnabled(False)

    def splittingUI(self):
        index = self.comboBoxSplittingMethod.currentIndex()
        if index == 0: # FFmpeg Scene Detection
            self.doubleSpinBoxFFmpegSceneThreshold.show()
            self.labelSplittingThreshold.show()
            self.labelSplittingChunkLength.hide()
            self.spinBoxChunking.hide()
            self.checkBoxSplittingReencode.hide()
            self.comboBoxSplittingReencode.hide()
        elif index == 1: # Equal Chunking
            self.doubleSpinBoxFFmpegSceneThreshold.hide()
            self.labelSplittingThreshold.hide()
            self.labelSplittingChunkLength.show()
            self.spinBoxChunking.show()
            self.checkBoxSplittingReencode.show()
            self.comboBoxSplittingReencode.show()

    def openVideoSource(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Select Video File', '',"Video files (*.mp4 *.mkv *.flv *.mov)")
        if fname:
            self.labelVideoSource.setText(fname)
            self.videoInput = fname
            self.tempDirFileName = os.path.splitext(os.path.basename(fname))[0]
            self.ffprobeAudioDetect()

    def setVideoDestination(self):
        fname, _ = QFileDialog.getSaveFileName(self, 'Select Video Output', '',"Video files (*.webm *.mp4 *.mkv)")
        self.labelVideoDestination.setText(fname)
        self.videoOutput = fname

    #  ════════════════════════════════════════ Filters ═══════════════════════════════════════

    def setVideoFilters(self):
        crop = self.groupBoxCrop.isChecked() is True
        resize = self.groupBoxResize.isChecked() is True
        deinterlace = self.groupBoxDeinterlace.isChecked() is True
        rotate = self.groupBoxRotate.isChecked() is True
        counter = 0
        filter_command = ""

        if crop or resize or deinterlace or rotate:
            filter_command = " -vf "
            if crop:
                filter_command += self.VideoCrop()
                counter += 1
            if deinterlace:
                if counter != 0:
                    filter_command += ","
                filter_command += self.VideoDeinterlace()
                counter += 1
            if rotate:
                if counter != 0:
                    filter_command += ","
                filter_command += self.VideoRotate()
                counter += 1
            if resize:
                if counter != 0:
                    filter_command += ","
                filter_command += self.VideoResize() # !!! Has to be last, else ffmpeg logic fails
        self.filterCommand = filter_command

    def VideoCrop(self):
        if self.groupBoxCrop.isChecked() is True:
            width_new = str(self.spinBoxFilterCropRight.value() + self.spinBoxFilterCropLeft.value())
            height_new = str(self.spinBoxFilterCropTop.value() + self.spinBoxFilterCropBottom.value())
            return "crop=iw-" + width_new + ":ih-" + height_new + ":" + str(self.spinBoxCropLeft.value()) + ":" + str(self.spinBoxCropTop.value())
        else:
            return None  # Needs to be set, else it will crop if in the same instance it was active

    def VideoResize(self):
        if self.groupBoxResize.isChecked() == True:
            return "scale=" + str(self.spinBoxFilterResizeWidth.value()) + ":" + str(self.spinBoxFilterResizeHeight.value())
        else:
            return None

    def VideoDeinterlace(self):
        if self.groupBoxDeinterlace.isChecked() == True:
            return "yadif=" + self.comboBoxDeinterlace.currentText()
        else:
            return None

    def VideoRotate(self):
        if self.groupBoxRotate.isChecked() == True:
            if self.comboBoxRotate.currentIndex() == 0:
                return "transpose=1"
            elif self.comboBoxRotate.currentIndex() == 1:
                return "transpose=2"
            elif self.comboBoxRotate.currentIndex() == 2:
                return "transpose=2,transpose=2"
            else:
                return None # unimplemented

    #  ═══════════════════════════════════════ Splitting ══════════════════════════════════════
    
    def splitting(self):
        # Create Temp Folder if not existant
        out_path = Path(os.path.join(self.tempDir, self.tempDirFileName, "Chunks"))
        out_path.mkdir(parents=True, exist_ok=True)
        # Select the correct splitting method
        current_index = self.comboBoxSplittingMethod.currentIndex()
        if current_index == 0:
            # FFmpeg Scene Detect
            self.labelStatus.setText("Status: Detecting Scenes")
            self.ffmpegSceneDetect()
        elif current_index == 1:
            # Equal Chunking
            self.labelStatus.setText("Status: Splitting")
            self.ffmpegChunking()

    def ffmpegChunking(self):
        videoCodec = [ ]
        # Set Splitting Parameters
        if self.checkBoxSplittingReencode.isChecked() == True:
            if self.comboBoxSplittingReencode.currentIndex() == 0:
                videoCodec = ['libx264', '-crf', '0', '-preset', 'ultrafast']
            elif self.comboBoxSplittingReencode.currentIndex() == 1:
                videoCodec = ['ffv1', '-level', '3', '-threads', '6', '-coder', '1', '-context', '1', '-g', '1', '-slicecrc', '0', '-slices', '4']
            elif self.comboBoxSplittingReencode.currentIndex() == 2:
                videoCodec = ['utvideo']
        else:
            videoCodec = ['copy']
        segTime = str(self.spinBoxChunking.value())
        splittingOutput = os.path.join(self.tempDir, self.tempDirFileName, "Chunks", "split%6d.mkv")

        # Create a QThread object
        self.thread_split = QThread()
        # Create a worker object
        self.worker_split = worker_splitting.WorkerSplitting()
        # Move worker to the thread
        self.worker_split.moveToThread(self.thread_split)
        # Connect signals and slots
        self.thread_split.started.connect(partial(self.worker_split.run, self.videoInput, videoCodec, segTime, splittingOutput))
        self.worker_split.finished.connect(self.thread_split.quit)
        self.worker_split.finished.connect(self.ffmpegSplittingFinished)
        self.worker_split.finished.connect(self.worker_split.deleteLater)
        self.thread_split.finished.connect(self.thread_split.deleteLater)
        # Start the thread
        self.thread_split.start()

    def ffmpegSplittingFinished(self):
        self.setQueue()
        self.mainEncode()

    def ffmpegSceneDetect(self):
        threshold = str(self.doubleSpinBoxFFmpegSceneThreshold.value())
        splittingOutput = os.path.join(self.tempDir, self.tempDirFileName, "splits.txt")
        # Create a QThread object
        self.thread_scene_detect = QThread()
        # Create a worker object
        self.worker_scene_detect = worker_scene.WorkerScene()
        # Move worker to the thread
        self.worker_scene_detect.moveToThread(self.thread_scene_detect)
        # Connect signals and slots
        self.thread_scene_detect.started.connect(partial(self.worker_scene_detect.run, self.videoInput, threshold, splittingOutput))
        self.worker_scene_detect.finished.connect(self.thread_scene_detect.quit)
        self.worker_scene_detect.finished.connect(self.ffmpegSplittingFinished)
        self.worker_scene_detect.finished.connect(self.worker_scene_detect.deleteLater)
        self.thread_scene_detect.finished.connect(self.worker_scene_detect.deleteLater)
        # Start the thread
        self.thread_scene_detect.start()

    #  ═════════════════════════════════════════ Main ═════════════════════════════════════════
    def mainEntry(self):
        # Check if input and output is set
        if self.videoInput and self.videoOutput:
            self.progressBar.setValue(0)
            # Audio Encoding
            self.encode_audio()
        else:
            print("Not Implemented")

    #  ══════════════════════════════════ Command Generator ═══════════════════════════════════
    def setPipeColorFMT(self):
        fmt = None
        space = self.comboBoxColorFormat.currentIndex()
        if space == 0:
            fmt = "yuv420p"
        elif space == 1:
            fmt = "yuv422p"
        elif space == 2:
            fmt = "yuv444p"
        depth = self.comboBoxBitDepth.currentIndex()
        if depth == 0:
            fmt += " -strict -1"
        elif depth == 1:
            fmt += "10le -strict -1"
        elif depth == 2:
            fmt += "12le -strict -1"
        self.pipeColorFMT = fmt

    def setEncoderSettings(self):
        encoder = self.comboBoxEncoder.currentIndex()
        fmt = self.comboBoxColorFormat.currentIndex()
        passes = self.comboBoxPasses.currentIndex()
        settings = None
        if encoder == 0: # aomenc 
            if passes == 0:
                self.encoder_passes = " --passes=1 "
            elif passes == 1:
                self.encoder_passes = " --passes=2 "
                self.encoderPassOne = " --pass=1 "
                self.encoderPassTwo = " --pass=2 "

            self.encoderOutput = " --output="
            self.encoderOutputStats = " --fpf="
            settings = "aomenc - --bit-depth=" + self.comboBoxBitDepth.currentText()

            if fmt == 0: # Color Format
                settings += " --i420"
            elif fmt == 1:
                settings += " --i422"
            elif fmt == 2:
                settings += " --i444"
            settings += " --cpu-used=" + str(self.horizontalSliderEncoderSpeed.value())

            if self.radioButtonCQ.isChecked() == True:
                settings += " --end-usage=q --cq-level=" + str(self.horizontalSliderQ.value())
            elif self.radioButtonVBR.isChecked() == True:
                settings += " --end-usage=vbr --target-bitrate=" + str(self.spinBoxVBR.value())

            if self.checkBoxAdvancedSettings.isChecked() == False:
                # Basic Settings
                settings += " --threads=4 --tile-columns=1 --tile-rows=2 "
            else:
                # Advanced Settings
                settings += " --threads=" + str(self.comboBoxAomencThreads.currentIndex())                  # Threads
                settings += " --tile-rows=" + str(self.comboBoxAomencTileRows.currentIndex())               # Tile Rows
                settings += " --tile-columns=" + str(self.comboBoxAomencTileCols.currentIndex())            # Tile Columns
                settings += " --kf-max-dist=" + str(self.spinBoxAomencGOP.value())                          # Max GOP
                settings += " --lag-in-frames=" + str(self.spinBoxAomencLagInFrames.value())                # Frame Buffer
                settings += " --tune=" + self.comboBoxAomencTune.currentText()                              # Tune
                settings += " --aq-mode=" + str(self.comboBoxAomencAQMode.currentIndex())                   # AQ Mode
                settings += " --color-primaries=" + self.comboBoxAomencColorPrimaries.currentText()         # Color Primaries
                settings += " --transfer-characteristics=" + self.comboBoxAomencColorTransfer.currentText() # Color Transfer
                settings += " --matrix-coefficients=" + self.comboBoxAomencColorMatrix.currentText()        # Color Matrix
                if self.checkBoxAomencDenoise.isChecked() == True:
                    settings += " --denoise-noise-level=" + str(self.spinBoxAomencDenoise.value())          # Denoise Noise Level
        elif encoder == 1: # rav1e
            self.encoderOutput = " --output "
            self.encoder_passes = " " # rav1e still does not support 2pass encoding
            settings = "rav1e - --speed " + str(self.horizontalSliderEncoderSpeed.value())
            if self.radioButtonCQ.isChecked() == True:
                settings += " --quantizer " + str(self.horizontalSliderQ.value())
            elif self.radioButtonVBR.isChecked() == True:
                settings += " --bitrate " + str(self.spinBoxVBR.value())

            if self.checkBoxAdvancedSettings.isChecked() == False:
                # Basic Settings
                settings += " --threads 4 --tile-cols 1 --tile-rows 2"
            else:
                # Advanced Settings
                settings += " --threads " + str(self.comboBoxRav1eThreads.currentIndex())                   # Threads
                settings += " --tile-rows " + str(self.comboBoxRav1eTileRows.currentIndex())                # Tile Rows
                settings += " --tile-cols " + str(self.comboBoxRav1eTileCols.currentIndex())                # Tile Columns
                settings += " --keyint " + str(self.spinBoxRav1eGOP.value())                                # Max GOP
                settings += " --range " + self.comboBoxRav1eRange.currentText()                             # Color Range
                settings += " --primaries " + self.comboBoxRav1eColorPrimaries.currentText()                # Color Primaries
                settings += " --transfer " + self.comboBoxRav1eColorTransfer.currentText()                  # Color Transfer
                settings += " --matrix " + self.comboBoxRav1eColorMatrix.currentText()                      # Color Matrix
                settings += " --tune " + self.comboBoxRav1eTune.currentText()                               # Tune
                if self.checkBoxRav1eContentLight.isChecked() == True:
                    settings += " --content-light " + str(self.spinBoxRav1eCll.value())                     # Content Light Cll
                    settings += "," + str(self.spinBoxRav1eFall.value())                                    # Content Light Fall
                if self.groupBoxRav1eMastering.isChecked() == True:
                    settings += " --mastering-display G(" + str(self.spinBoxRav1eMasteringGx.value()) + "," # Mastering Gx
                    settings += str(self.spinBoxRav1eMasteringGy.value()) + ")B("                           # Mastering Gy
                    settings += str(self.spinBoxRav1eMasteringBx.value()) + ","                             # Mastering Bx
                    settings += str(self.spinBoxRav1eMasteringBy.value()) + ")R("                           # Mastering By
                    settings += str(self.spinBoxRav1eMasteringRx.value()) + ","                             # Mastering Rx
                    settings += str(self.spinBoxRav1eMasteringRy.value()) + ")WP("                          # Mastering Ry
                    settings += str(self.spinBoxRav1eMasteringWPx.value()) + ","                            # Mastering WPx
                    settings += str(self.spinBoxRav1eMasteringWPy.value()) + ")L("                          # Mastering WPy
                    settings += str(self.spinBoxRav1eMasteringLx.value()) + ","                             # Mastering Lx
                    settings += str(self.spinBoxRav1eMasteringLy.value()) + ")"                             # Mastering Ly
        elif encoder == 2: # svt-av1
            if passes == 0:
                self.encoder_passes = " --passes 1 "
            elif passes == 1:
                self.encoder_passes = " --irefresh-type 2 --passes 2 "
                self.encoderPassOne = " --pass 1 "
                self.encoderPassTwo = " --pass 2 "
            self.encoderOutput = " -b "
            settings = "SvtAv1EncApp -i stdin --preset " + str(self.horizontalSliderEncoderSpeed.value())
            if self.radioButtonCQ.isChecked() == True:
                settings += " --rc 0 -q " + str(self.horizontalSliderQ.value())
            elif self.radioButtonVBR.isChecked() == True:
                settings += " --rc 1 --tbr " + str(self.spinBoxVBR.value())
            if self.checkBoxRav1eContentLight.isChecked() == False:
                settings += " --tile-columns " + str(self.comboBoxSvtTileCols.currentIndex())
                settings += " --tile-rows " + str(self.comboBoxSvtTileRows.currentIndex())
                settings += " --keyint " + str(self.spinBoxSvtGOP.value())
                settings += " --adaptive-quantization " + str(self.comboBoxSvtAQ.currentIndex())
        self.encoderSettings = settings

    def setQueue(self):
        # Clear Queue
        self.video_queue_first_pass = []
        self.video_queue_second_pass = []

        self.setVideoFilters()
        self.setPipeColorFMT()

        if self.groupBoxCustomSettings.isChecked():
            self.encoderSettings = self.textEditCustomSettings.text()
        else:
            self.setEncoderSettings()

        passes = self.comboBoxPasses.currentIndex()
        currentIndex = self.comboBoxSplittingMethod.currentIndex()
        encoder = self.comboBoxEncoder.currentIndex()

        if currentIndex == 0:
            # FFmpeg Scene Detect
            with open(os.path.join(self.tempDir, self.tempDirFileName, "splits.txt")) as f:
                counter = 0
                for seekPoint in f:
                    outFileName = str(counter).zfill(6)
                    tempInputFile = '\u0022' + self.videoInput + '\u0022'
                    tempOutputFile = '\u0022' + os.path.join(self.tempDir, self.tempDirFileName, "Chunks", "split" + outFileName + ".ivf") + '\u0022'
                    if passes == 0:
                        if encoder == 2: # svt-av1 specific
                            self.video_queue_first_pass.append("ffmpeg -i " + tempInputFile + " " + seekPoint.rstrip() + " -pix_fmt " + self.pipeColorFMT + " " + self.filterCommand + " -color_range 0 -vsync 0 -nostdin -f yuv4mpegpipe - | " + self.encoderSettings + self.encoder_passes + self.encoderOutput + tempOutputFile)
                        else:
                            self.video_queue_first_pass.append("ffmpeg -i " + tempInputFile + " " + seekPoint.rstrip() + " -pix_fmt " + self.pipeColorFMT + " " + self.filterCommand + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoderSettings + self.encoder_passes + self.encoderOutput + tempOutputFile)
                    elif passes == 1:
                        tempOutputFileLog = '\u0022' + os.path.join(self.tempDir, self.tempDirFileName, "Chunks", "split" + outFileName + ".stats") + '\u0022'
                        if encoder == 2: # svt-av1 specific
                            self.video_queue_first_pass.append("ffmpeg -i " + tempInputFile + " " + seekPoint.rstrip() + " -pix_fmt " + self.pipeColorFMT + " " + self.filterCommand + " -color_range 0 -vsync 0 -nostdin -f yuv4mpegpipe - | " + self.encoderSettings + self.encoder_passes + self.encoderPassOne + self.encoderOutput + "/dev/null " + self.encoderOutputStats + tempOutputFileLog)
                            self.video_queue_second_pass.append("ffmpeg -i " + tempInputFile + " " + seekPoint.rstrip() + " -pix_fmt " + self.pipeColorFMT + " " + self.filterCommand + " -color_range 0 -vsync 0 -nostdin -f yuv4mpegpipe - | " + self.encoderSettings + self.encoder_passes + self.encoderPassTwo + self.encoderOutput + tempOutputFile + self.encoderOutputStats + tempOutputFileLog)
                        else:
                            self.video_queue_first_pass.append("ffmpeg -i " + tempInputFile + " " + seekPoint.rstrip() + " -pix_fmt " + self.pipeColorFMT + " " + self.filterCommand + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoderSettings + self.encoder_passes + self.encoderPassOne + self.encoderOutput + "/dev/null " + self.encoderOutputStats + tempOutputFileLog)
                            self.video_queue_second_pass.append("ffmpeg -i " + tempInputFile + " " + seekPoint.rstrip() + " -pix_fmt " + self.pipeColorFMT + " " + self.filterCommand + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoderSettings + self.encoder_passes + self.encoderPassTwo + self.encoderOutput + tempOutputFile + self.encoderOutputStats + tempOutputFileLog)
                    counter += 1
        elif currentIndex == 1:
            # Equal Chunking
            files = os.listdir(os.path.join(self.tempDir, self.tempDirFileName, "Chunks"))
            # Iterate over all mkv files
            for file in files:
                if file.endswith(".mkv"):
                    tempInputFile = '\u0022' + os.path.join(self.tempDir, self.tempDirFileName, "Chunks", file) + '\u0022'
                    tempOutputFile = '\u0022' + os.path.join(self.tempDir, self.tempDirFileName, "Chunks", os.path.splitext(os.path.basename(str(file)))[0] + ".ivf") + '\u0022'
                    if passes == 0:
                        if encoder == 2: # svt-av1 specific
                            self.video_queue_first_pass.append("ffmpeg -i " + tempInputFile + " -pix_fmt " + self.pipeColorFMT + " -color_range 0 -vsync 0 -nostdin -f yuv4mpegpipe - | " + self.encoderSettings + self.encoder_passes + self.encoderOutput + tempOutputFile)
                        else:
                            self.video_queue_first_pass.append("ffmpeg -i " + tempInputFile + " -pix_fmt " + self.pipeColorFMT + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoderSettings + self.encoder_passes + self.encoderOutput + tempOutputFile)
                    elif passes == 1:
                        tempOutputFileLog = '\u0022' + os.path.join(self.tempDir, self.tempDirFileName, "Chunks", os.path.splitext(os.path.basename(str(file)))[0] + ".stats") + '\u0022'
                        if encoder == 2: # svt-av1 specific
                            self.video_queue_first_pass.append("ffmpeg -i " + tempInputFile + " -pix_fmt " + self.pipeColorFMT + " -color_range 0 -vsync 0 -nostdin -f yuv4mpegpipe - | " + self.encoderSettings + self.encoder_passes + self.encoderPassOne + self.encoderOutput + "/dev/null " + self.encoderOutputStats + tempOutputFileLog)
                            self.video_queue_second_pass.append("ffmpeg -i " + tempInputFile + " -pix_fmt " + self.pipeColorFMT + " -color_range 0 -vsync 0 -nostdin -f yuv4mpegpipe - | " + self.encoderSettings + self.encoder_passes + self.encoderPassTwo + self.encoderOutput + tempOutputFile + self.encoderOutputStats + tempOutputFileLog)
                        else:
                            self.video_queue_first_pass.append("ffmpeg -i " + tempInputFile + " -pix_fmt " + self.pipeColorFMT + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoderSettings + self.encoder_passes + self.encoderPassOne + self.encoderOutput + "/dev/null " + self.encoderOutputStats + tempOutputFileLog)
                            self.video_queue_second_pass.append("ffmpeg -i " + tempInputFile + " -pix_fmt " + self.pipeColorFMT + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoderSettings + self.encoder_passes + self.encoderPassTwo + self.encoderOutput + tempOutputFile + self.encoderOutputStats + tempOutputFileLog)

    #  ═══════════════════════════════════════ Encoding ═══════════════════════════════════════
    def mainEncode(self):
        self.labelStatus.setText("Status: Encoding")

        poolSize = self.comboBoxWorkerCount.currentIndex() + 1
        queueOne = self.video_queue_first_pass
        queueTwo = self.video_queue_second_pass

        self.progressBar.setMaximum(len(queueOne) + len(queueTwo))

        # Create a QThread object
        self.thread = QThread()
        # Create a worker object
        self.worker = worker.Worker()
        # Move worker to the thread
        self.worker.moveToThread(self.thread)
        # Connect signals and slots
        self.thread.started.connect(partial(self.worker.run, poolSize, queueOne, queueTwo))
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.workerFinished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.progress.connect(self.reportProgress)
        # Start the thread
        self.thread.start()

    def workerFinished(self):
        self.labelStatus.setText("Status: Muxing")
        self.mainMuxing()
        self.labelStatus.setText("Status: Finished")

    #  ════════════════════════════════════════ Muxing ════════════════════════════════════════
    def mainMuxing(self):
        # Creates the list file of all encoded chunks for ffmpeg concat
        files = os.listdir(os.path.join(self.tempDir, self.tempDirFileName, "Chunks"))
        f = open(os.path.join(self.tempDir, self.tempDirFileName, "Chunks", "mux.txt"), "a")
        sorted_files = sorted(files)
        for file in sorted_files:
            if file.endswith(".ivf"):
                tempInputFile = '\u0027' + os.path.join(self.tempDir, self.tempDirFileName, "Chunks", file) + '\u0027'
                f.write("file " + tempInputFile + "\n")
        f.close()
        if self.audio_encoding:
            temp_video = os.path.join(self.tempDir, self.tempDirFileName, "temp.mkv")
            temp_audio = os.path.join(self.tempDir, self.tempDirFileName, "Audio", "audio.mkv")
            subprocess.call(['ffmpeg', '-y','-f', 'concat', '-safe', '0', '-i', os.path.join(self.tempDir, self.tempDirFileName, "Chunks", "mux.txt"), '-c', 'copy', temp_video])
            subprocess.call(['ffmpeg', '-y','-i', temp_video, '-i', temp_audio, '-c', 'copy', self.videoOutput])
        else:
            subprocess.call(['ffmpeg', '-y','-f', 'concat', '-safe', '0', '-i', os.path.join(self.tempDir, self.tempDirFileName, "Chunks", "mux.txt"), '-c', 'copy', self.videoOutput])


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = neav1e()
    app.exec_()
