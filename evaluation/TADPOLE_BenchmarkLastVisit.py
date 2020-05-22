#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pandas as pd
import numpy as np
import os
import sys

import datetime as dt
from dateutil.relativedelta import relativedelta

# Benchmark entry added after the competition deadline. The entry simply uses the last known value.
# Based on an MATLAB script by Daniel Alexander and Neil Oxtoby.
# ============
# Authors:
#   Razvan Valentin-Marinescu

## Read in the TADPOLE data set and extract a few columns of salient information.
# Script requires that TADPOLE_D1_D2.csv is in the parent directory. Change if
# necessary
dataLocationD1D2 = '../'  # parent directory

tadpoleD1D2File = os.path.join(dataLocationD1D2, 'TADPOLE_D1_D2.csv')
outputFile = 'TADPOLE_Submission_BenchmarkLastVisit-ID-1.csv'

errorFlag = 0
if not os.path.exists(tadpoleD1D2File):
  print('File {0} does not exist! \nYou need to download it from ADNI\n and/or move it in the right directory'.format(
    tadpoleD1D2File))
  errorFlag = 1
if errorFlag:
  sys.exit()

# choose whether to display warning messages
verbose = 0

# * Read in the D1_D2 spreadsheet: may give a DtypeWarning, but the read/import works.
# * This file contains all the necessary data - the TADPOLE_LB1_LB2.csv spreadsheet contains
# * only the LB1 and LB2 indicators, aligned to TADPOLE_D1_D2.csv
TADPOLE_Table = pd.read_csv(tadpoleD1D2File, low_memory=False)

# * Target variables: convert strings to numeric if necessary
targetVariables = ['DX', 'ADAS13', 'Ventricles']
variablesToCheck = ['RID', 'ICV_bl'] + targetVariables  # also check RosterID and IntraCranialVolume
for kt in range(0, len(variablesToCheck)):
  var0 = TADPOLE_Table[variablesToCheck[kt]][0]
  if not ('DX' == variablesToCheck[kt]):
    if np.str(var0) == var0:
      # * Convert strings to numeric
      TADPOLE_Table[variablesToCheck[kt]] = np.int(TADPOLE_Table[variablesToCheck[kt]])

# * Copy numeric target variables into arrays. Missing data is encoded as -1
# ADAS13 scores
ADAS13_Col = TADPOLE_Table.ADAS13.values.copy()
ADAS13_Col[np.isnan(ADAS13_Col)] = -1
# Ventricles volumes, normalised by intracranial volume
Ventricles_Col = TADPOLE_Table.Ventricles.values.copy()
Ventricles_Col[np.isnan(Ventricles_Col)] = -1
ICV_Col = TADPOLE_Table.ICV_bl.values.copy()
ICV_Col[np.isnan(ICV_Col)] = -1
ICV_Col[Ventricles_Col == -1] = 1
Ventricles_ICV_Col = Ventricles_Col / ICV_Col
# * Create an array containing the clinical status column from the spreadsheet
# DXCHANGE: current diagnosis (DX) and change since most recent visit, i.e., '[previous DX] to [current DX]'
DXCHANGE = TADPOLE_Table.DX.values.copy()  # 'NL to MCI', 'MCI to Dementia', etc.
DX = DXCHANGE.copy()  # Note: missing data encoded numerically (!) as nan
# Convert DXCHANGE to current DX
for kr in range(0, len(DX)):
  if np.isreal(DX[kr]):  # Missing data
    DX[kr] = ''  # missing data encoded as empty string
  else:
    # Loop until finding the final space in the DXCHANGE string
    idxn = 0  # reset
    while not (idxn == -1):
      idx = idxn
      idxn = DX[kr].find(' ', idxn + 1)
    if idx > 0:
      idx = idx + 1
    DX[kr] = DX[kr][idx:]  # extract current DX from DXCHANGE
CLIN_STAT_Col = DX.copy()

# * Copy the subject ID column from the spreadsheet into an array.
RID_Col = TADPOLE_Table.RID.values.copy()
RID_Col[np.isnan(RID_Col)] = -1  # missing data encoded as -1

# * Compute months since Jan 2000 for each exam date
ref = dt.datetime(2000, 1, 1)
EXAMDATE = TADPOLE_Table.EXAMDATE.values.copy()
ExamMonth_Col = np.zeros(len(EXAMDATE))
for k in range(0, len(EXAMDATE)):
  d = dt.datetime.strptime(EXAMDATE[k], '%Y-%m-%d') - ref
  ExamMonth_Col[k] = d.days / 365 * 12

# * Copy the column specifying membership of LB2 into an array.
D2_col = TADPOLE_Table.D2 == 1


## Generate the very simple forecast
print('Generating forecast ...')

# * Get the list of subjects to forecast from LB2 - the ordering is the
# * same as in the submission template.
d2Inds = np.where(D2_col)[0]
D2_SubjList = np.unique(RID_Col[d2Inds])
N_D2 = len(D2_SubjList)

# * Create arrays to contain the 84 monthly forecasts for each LB2 subject
nForecasts = 5 * 12  # forecast 5 years (84 months).
# 1. Clinical status forecasts
#    i.e. relative likelihood of NL, MCI, and Dementia (3 numbers)
CLIN_STAT_forecast = np.zeros([N_D2, nForecasts, 3])
# 2. ADAS13 forecasts
#    (best guess, upper and lower bounds on 50% confidence interval)
ADAS13_forecast = np.zeros([N_D2, nForecasts, 3])
# 3. Ventricles volume forecasts
#    (best guess, upper and lower bounds on 50% confidence interval)
Ventricles_ICV_forecast = np.zeros([N_D2, nForecasts, 3])

# * Our example forecast for each subject is based on the most recent
# * available (not missing) data for each target variable in LB2.

# * Extract most recent data.
# Initialise storage arrays
most_recent_CLIN_STAT = N_D2 * ['']
most_recent_ADAS13 = -1 * np.ones([N_D2, 1])
most_recent_Ventricles_ICV = -1 * np.zeros([N_D2, 1])

display_info = 0  # Useful for checking and debugging (see below)

# *** Defaults - in case of missing data
# * Ventricles
# Missing data = typical volume +/- broad interval = 25000 +/- 20000
Ventricles_typical = 25000
Ventricles_broad_50pcMargin = 20000  # +/- (broad 50% confidence interval)
# Default CI = 1000
Ventricles_default_50pcMargin = 1000  # +/- (broad 50% confidence interval)
# Convert to Ventricles/ICV via linear regression
nm = np.all(np.stack([Ventricles_Col > 0, ICV_Col > 0]), 0)  # not missing: Ventricles and ICV
x = Ventricles_Col[nm]
y = Ventricles_ICV_Col[nm]
lm = np.polyfit(x, y, 1)
p = np.poly1d(lm)

Ventricles_ICV_typical = p(Ventricles_typical)
Ventricles_ICV_broad_50pcMargin = np.abs(p(Ventricles_broad_50pcMargin) - p(-Ventricles_broad_50pcMargin)) / 2
Ventricles_ICV_default_50pcMargin = np.abs(p(Ventricles_default_50pcMargin) - p(-Ventricles_default_50pcMargin)) / 2
# * ADAS13
ADAS13_typical = 12
ADAS13_typical_lower = ADAS13_typical - 10
ADAS13_typical_upper = ADAS13_typical + 10

for i in range(0, N_D2):  # Each subject in LB2
  # * Rows in LB2 corresponding to Subject LB2_SubjList(i)
  subj_rows = np.where(np.all(np.stack([RID_Col == D2_SubjList[i], D2_col], 0), 0))[0]
  subj_exam_dates = ExamMonth_Col[subj_rows]
  # Non-empty data among these rows
  exams_with_CLIN_STAT = CLIN_STAT_Col[subj_rows] != ''
  exams_with_ADAS13 = ADAS13_Col[subj_rows] > 0
  exams_with_ventsv = Ventricles_ICV_Col[subj_rows] > 0
  # exams_with_allData   = exams_with_CLIN_STAT & exams_with_ADAS13 & exams_with_ventsv

  # * Extract most recent non-empty data
  # 1. Clinical status
  if sum(exams_with_CLIN_STAT) >= 1:  # Subject has a Clinical status
    # Index of most recent visit with a Clinical status
    ind = subj_rows[
      np.all(np.stack([subj_exam_dates == max(subj_exam_dates[exams_with_CLIN_STAT]), exams_with_CLIN_STAT], 0), 0)]
    most_recent_CLIN_STAT[i] = CLIN_STAT_Col[ind[-1]]
  else:  # Subject has no Clinical statuses in the data set
    most_recent_CLIN_STAT[i] = ''  # Already set when initialised above

  # 2. ADAS13 score
  if sum(exams_with_ADAS13) >= 1:  # Subject has an ADAS13 score
    # Index of most recent visit with an ADAS13 score
    ind = subj_rows[
      np.all(np.stack([subj_exam_dates == max(subj_exam_dates[exams_with_ADAS13]), exams_with_ADAS13], 0), 0)]
    most_recent_ADAS13[i] = ADAS13_Col[ind[-1]]
  else:  # Subject has no ADAS13 scores in the data set
    most_recent_ADAS13[i] = -1  # Already set when initialised above
  # 3. Most recent ventricles volume measurement
  if sum(exams_with_ventsv) >= 1:  # Subject has a ventricles volume recorded
    # Index of most recent visit with a ventricles volume
    ind = subj_rows[
      np.all(np.stack([subj_exam_dates == max(subj_exam_dates[exams_with_ventsv]), exams_with_ventsv], 0), 0)]
    most_recent_Ventricles_ICV[i] = Ventricles_ICV_Col[ind[-1]]
  else:  # Subject has no ventricle volume measurement in the data set
    most_recent_Ventricles_ICV[i] = -1  # Already set when initialised above

  # * "Debug mode": prints out some stuff (set display_info=1 above)
  if display_info:
    ExamMonth_Col[subj_rows]
    CLIN_STAT_Col[subj_rows]
    Ventricles_ICV_Col[subj_rows]
    ADAS13_Col[subj_rows]
    print(
      '{0} - CLIN_STAT {1} - ADAS13 {2} - Ventricles_ICV {3}'.format(i, most_recent_CLIN_STAT[i], most_recent_ADAS13[i],
                                                                     most_recent_Ventricles_ICV[i]))

  # *** Construct example forecasts
  # * Clinical status forecast: predefined likelihoods per current status
  if most_recent_CLIN_STAT[i] == 'NL':
    CNp, MCIp, ADp = [1, 0, 0]
  elif most_recent_CLIN_STAT[i] == 'MCI':
    CNp, MCIp, ADp = [0, 1, 0]
  elif most_recent_CLIN_STAT[i] == 'Dementia':
    CNp, MCIp, ADp = [0, 0, 1]
  else:
    CNp, MCIp, ADp = [0.33, 0.33, 0.34]
    if verbose:
      print('Unrecognised status ' + most_recent_CLIN_STAT[i])
  # Use the same clinical status probabilities for all months
  CLIN_STAT_forecast[i, :, 0] = CNp
  CLIN_STAT_forecast[i, :, 1] = MCIp
  CLIN_STAT_forecast[i, :, 2] = ADp
  # * ADAS13 forecast: = most recent score, default confidence interval
  if most_recent_ADAS13[i] >= 0:
    ADAS13_forecast[i, :, 0] = most_recent_ADAS13[i]
    ADAS13_forecast[i, :, 1] = max([0, most_recent_ADAS13[i] - 1])  # Set to zero if best-guess less than 1.
    ADAS13_forecast[i, :, 2] = most_recent_ADAS13[i] + 1
  else:
    # Subject has no history of ADAS13 measurement, so we'll take a
    # typical score of 12 with wide confidence interval +/-10.
    ADAS13_forecast[i, :, 0] = ADAS13_typical
    ADAS13_forecast[i, :, 1] = ADAS13_typical_lower
    ADAS13_forecast[i, :, 2] = ADAS13_typical_upper
  # * Ventricles volume forecast: = most recent measurement, default confidence interval
  if most_recent_Ventricles_ICV[i] > 0:
    Ventricles_ICV_forecast[i, :, 0] = most_recent_Ventricles_ICV[i]
    Ventricles_ICV_forecast[i, :, 1] = most_recent_Ventricles_ICV[i] - Ventricles_ICV_default_50pcMargin
    Ventricles_ICV_forecast[i, :, 2] = most_recent_Ventricles_ICV[i] + Ventricles_ICV_default_50pcMargin
  else:
    # Subject has no imaging history, so we'll take a typical
    # ventricles volume of 25000 & wide confidence interval +/-20000
    Ventricles_ICV_forecast[i, :, 0] = Ventricles_ICV_typical
    Ventricles_ICV_forecast[i, :, 1] = Ventricles_ICV_typical - Ventricles_ICV_broad_50pcMargin
    Ventricles_ICV_forecast[i, :, 2] = Ventricles_ICV_typical + Ventricles_ICV_broad_50pcMargin

Ventricles_ICV_forecast = np.around(1e9 * Ventricles_ICV_forecast,
                                    0) / 1e9  # round to 9 decimal places to match MATLAB equivalent

## Now construct the forecast spreadsheet and output it.
print('Constructing the output spreadsheet {0} ...'.format(outputFile))
submission_table = pd.DataFrame()
# * Repeated matrices - compare with submission template
submission_table['RID'] = D2_SubjList.repeat(nForecasts)
submission_table['ForecastMonth'] = np.tile(range(1, nForecasts + 1), (N_D2, 1)).flatten()
# * Submission dates - compare with submission template
startDate = dt.datetime(2018, 1, 1)
endDate = startDate + relativedelta(months=+nForecasts - 1)
ForecastDates = [startDate]
while ForecastDates[-1] < endDate:
  ForecastDates.append(ForecastDates[-1] + relativedelta(months=+1))
ForecastDatesStrings = [dt.datetime.strftime(d, '%Y-%m') for d in ForecastDates]
submission_table['ForecastDate'] = np.tile(ForecastDatesStrings, (N_D2, 1)).flatten()
# * Pre-fill forecast data, encoding missing data as NaN
nanColumn = np.repeat(np.nan, submission_table.shape[0])
submission_table['CNRelativeProbability'] = nanColumn
submission_table['MCIRelativeProbability'] = nanColumn
submission_table['ADRelativeProbability'] = nanColumn
submission_table['ADAS13'] = nanColumn
submission_table['ADAS1350_CILower'] = nanColumn
submission_table['ADAS1350_CIUpper'] = nanColumn
submission_table['Ventricles_ICV'] = nanColumn
submission_table['Ventricles_ICV50_CILower'] = nanColumn
submission_table['Ventricles_ICV50_CIUpper'] = nanColumn

# *** Paste in month-by-month forecasts **
# * 1. Clinical status
submission_table['CNRelativeProbability'] = CLIN_STAT_forecast[:, :, 0].flatten()
submission_table['MCIRelativeProbability'] = CLIN_STAT_forecast[:, :, 1].flatten()
submission_table['ADRelativeProbability'] = CLIN_STAT_forecast[:, :, 2].flatten()
# * 2. ADAS13 score
submission_table['ADAS13'] = ADAS13_forecast[:, :, 0].flatten()
# Lower and upper bounds (50% confidence intervals)
submission_table['ADAS1350_CILower'] = ADAS13_forecast[:, :, 1].flatten()
submission_table['ADAS1350_CIUpper'] = ADAS13_forecast[:, :, 2].flatten()
# * 3. Ventricles volume (normalised by intracranial volume)
submission_table['Ventricles_ICV'] = Ventricles_ICV_forecast[:, :, 0].flatten()
# Lower and upper bounds (50% confidence intervals)
submission_table['Ventricles_ICV50_CILower'] = Ventricles_ICV_forecast[:, :, 1].flatten()
submission_table['Ventricles_ICV50_CIUpper'] = Ventricles_ICV_forecast[:, :, 2].flatten()

# * Convert all numbers to strings - only useful in MATLAB
# hdr = submission_table.columns.copy()
# for k in range(0,len(hdr)):
#     if np.all(np.isreal(submission_table[hdr[k]].values)):
#         submission_table[hdr[k]] = submission_table[hdr[k]].values.astype(str)

# * Use column names that match the submission template
submission_table.rename(columns={'RID': 'RID',
                                 'ForecastMonth': 'Forecast Month',
                                 'ForecastDate': 'Forecast Date',
                                 'CNRelativeProbability': 'CN relative probability',
                                 'MCIRelativeProbability': 'MCI relative probability',
                                 'ADRelativeProbability': 'AD relative probability',
                                 'ADAS13': 'ADAS13',
                                 'ADAS1350_CILower': 'ADAS13 50% CI lower',
                                 'ADAS1350_CIUpper': 'ADAS13 50% CI upper',
                                 'Ventricles_ICV': 'Ventricles_ICV',
                                 'Ventricles_ICV50_CILower': 'Ventricles_ICV 50% CI lower',
                                 'Ventricles_ICV50_CIUpper': 'Ventricles_ICV 50% CI upper'}, inplace=True)
# * Write to file
submission_table.to_csv(outputFile, index=False)


print('Evaluate predictions')
from datetime import datetime
d4Df=pd.read_csv('./TADPOLE_D4_corr.csv')

d4Df['CognitiveAssessmentDate'] = [datetime.strptime(x, '%Y-%m-%d') for x in d4Df['CognitiveAssessmentDate']]
d4Df['ScanDate'] = [datetime.strptime(x, '%Y-%m-%d') for x in d4Df['ScanDate']]
mapping = {'CN': 0, 'MCI': 1, 'AD': 2}
d4Df.replace({'Diagnosis': mapping}, inplace=True)

import evalOneSubmission as eos
mAUC, bca, adasMAE, ventsMAE, adasWES, ventsWES, adasCPA, ventsCPA = eos.evalOneSub(d4Df,submission_table)

print('Diagnosis:')
print('mAUC = ' + "%0.3f" % mAUC)
print('BAC = ' + "%0.3f" % bca)
print('ADAS:')
print('MAE = ' + "%0.3f" % adasMAE)
print('WES = ' + "%0.3f" % adasWES)
print('CPA = ' + "%0.3f" % adasCPA)
print('VENTS:')
print('MAE = ' + "%0.3e" % ventsMAE)
print('WES = ' + "%0.3e" % ventsWES)
print('CPA = ' + "%0.3f" % ventsCPA)

