# -*- coding: utf-8 -*-
"""
Created on Fri Jan 27 07:16:51 2023

This script fetches the current schedule of classes for Annenberg's 8 programs in COMM and JOUR, then
splits the co-instructor teams, and cleans up the class times so they can be read as Start_time and End_time by Excel.
Requires multipart_names.csv present in working directory

@author: fbar
"""
import os
import csv
import re
import pandas as pd

# set parameters for this run
os.chdir("/Users/fbar/tmp/")
current_term = '20231' #for a single term

# parameters to form urls for fetching SoC
root = 'https://classes.usc.edu/term-'
directory = '/csv/'
programs = ('ascj','comm','cmgt','dmm','dsm','jour','pubd','pr') #adjust to retrieve selected programs
ext = '.csv'

# create a list of terms to import
# semesters = ('1','2','3')
# terms=[]
# for year in range(2017,2024): # startyear (2014 min - not available prior) to endyear+1
#     for s in semesters:
#         terms.append(str(year)+s)
        
# here we only need a single term; use commented code block above if need to fetch multiple terms
terms = (current_term,) 

combined = pd.DataFrame()

for t in terms:
    
    # for each term, build a list of urls for the various program SoCs csv
    # patterned after https://classes.usc.edu/term-20162/csv/comm.csv
    urls = []
    for p in programs:
        urls.append(root + t + directory + p + ext)

    # combine the csv schedules into one dataframe for that term
    combinedterm = pd.DataFrame()
    for url in urls:
        try:      # error handling for non-existent programs, e.g. DMM pre 2021; or not yet available SoC, e.g. Fall next year
            increment = pd.read_csv(url) 
        except:
            pass
        combinedterm = pd.concat([combinedterm, increment])
        increment = pd.DataFrame()

    # add a Term column
    combinedterm["Term"] = t

    #combine all Term dataframes into one
    combined = pd.concat([combined,combinedterm])
    
# FIRST PASS CLEAN-UP
# clean up extraneous characters in Instructor column
combined['Instructor'].replace(',','', regex=True, inplace=True)
combined['Instructor'].replace('</a>','', regex=True, inplace=True)

# downfill null cells in first 3 columns
for col in ['Course number', 'Course title', 'Units']:
    combined[col] = combined[col].ffill()
filled = combined

# remove rows where Instructor is null
df = filled[filled['Instructor'].notnull()]

# SPLIT CO-INSTRUCTORS, FIX INCONSISTENT NAMES AND NAME TYPOS
# build dictionary to turn multipart names into two-part names, and fix a few typos 
# e.g. replaces Jennifer de la Fuente with Jennifer de_la_Fuente, Eunjin (Anna) Kim with Eunjin_(Anna) Kim, etc.
# e.g. consoladiates "Joshua Kun" and "Josh Kun" into a single "Josh Kun"
# based on multipart_names.csv, which handles multipart names of instructors since 2014. 
# needs updating if new multipart-named instructors come along

reader = csv.DictReader(open('multipart_names.csv'))
dict = {}
for row in reader:
    dict[row['SoC_multipart_name']] = row['twopart_name']

df_new=df.replace(dict, regex=True)

# count number of co-instructors
# BUG: 4 OF Thomas Billard Jr CLASSES RESULT IN 1.5 co-instructors count
df_new['co-instructors'] = (df_new['Instructor'].str.count(" ", re.I) + 1)/2

# split instructors by 2-words chunks into new columns 
names = df_new['Instructor']
def splitter(s):
    spl = s.split()
    return [" ".join(spl[i:i+2]) for i in range(0, len(spl), 2)]
split_names = pd.DataFrame(names.apply(splitter).to_list())
df_new = df_new.reset_index()

df = pd.concat([df_new,split_names], axis=1)

# figure out how many new columns were created = max number of co-instructors in this set
max = int(df_new['co-instructors'].max())

# unpivot by split co-instructor columns
list = [i for i in range(max)]
keep_columns = ['Instructor', 'Days', 'Time', 'Room', 'Section', 'Course number', 'Course title', 'Type', 'Seats', 'Registered', 'co-instructors']
df_unpivot = pd.melt(df, id_vars=keep_columns, value_vars=list, value_name="Instr_unpivoted")

# clean up
df_unpivot = df_unpivot[df_unpivot['Instr_unpivoted'].notnull()]
df_unpivot['Instr_unpivoted'] = df_unpivot['Instr_unpivoted'].str.replace('_',' ')
df_unpivot.drop(['variable'], axis=1, inplace=True)

# rename columns - could be done earlier
df = df_unpivot.rename(columns={'Instructor': 'Instructor team', 'Instr_unpivoted': 'Instructor'})


# FIX CLASSES TIMES AND DAYS TO CREATE CONSISTENT Start_time AND End_time COLUMNS
# if last 2 characters of 'Time' are 'am', then start time is am
# otherwise:
# 	if start_hour is between 8 and 11, then start time is am
# 	otherwise:
# 		start time is pm

# create two new Start and End time columns
df['Start_time'] = df['Time']
df[['Start_time','End_time']] = df['Start_time'].str.split('-',expand=True)

# create variables 'amorpm' and 'start_hour' to perform test
df['amorpm'] = df['End_time'].str[-2:]
df['start_hour'] = df['Start_time'].str.split(':').str[0]

# format End_time so excel reads it as a time
df['End_time'] = df['End_time'].str[:-2] + " " + df['End_time'].str[-2:]

# if 'Time' says 'am', the start time is in the am
mask = (df['amorpm'] == 'am')
df.loc[mask, 'Start_time'] = df['Start_time'].astype(str) + ' am'

# if 'Time' says 'pm', and the Start Hour is between [8,11], then start time is am
mask = ((df['amorpm'] == 'pm') & (df['start_hour'].isin(['8', '9', '10', '11'])))
df.loc[mask, 'Start_time'] = df['Start_time'].astype(str) + ' am'

# all others cases, start time is pm
mask = ((df['amorpm'] == 'pm') & (~df['start_hour'].isin(['8', '9', '10', '11'])))
df.loc[mask, 'Start_time'] = df['Start_time'].astype(str) + ' pm'

# clean up times
df = df.drop(['amorpm', 'start_hour'], axis=1)

# clean up days       
dict = {
    'Fri, Sat' : 'Friday,Saturday', 
    'MTuW' : 'Monday,Tuesday,Wednesday', 
    'MTuWThF' : 'Monday,Tuesday,Wednesday,Thursday,Friday', 
    'Mon, Wed' : 'Monday,Wednesday', 
    'MWF' : 'Monday,Wednesday,Friday', 
    'Thu, Fri' : 'Thursday,Friday', 
    'Tue, Thu' : 'Tuesday,Thursday', 
    'TuThF' : 'Tuesday,Thursday,Friday', 
    'Wed, Fri' : 'Wednesday,Friday'
}

df=df.replace({"Days": dict})

# drop rows with 'Start_time' = TBA
df.drop(df[df['Start_time'] == 'TBA'].index, inplace = True)

# split Days into columns
single_days = df['Days'].str.split(',', expand=True)
df1 = pd.concat([df,single_days], axis=1)

df_unpivot = pd.melt(df1, id_vars=('Instructor','Start_time','End_time', 'Course number', 'Course title', 'Room', 'Section', 'Type', 'Seats', 'Registered', 'co-instructors', 'Instructor team'), value_vars=[0, 1])

#drop rows with 'value' null
df_unpivot = df_unpivot[df_unpivot['value'].notnull()]

# drop 'variable' column
df_unpivot = df_unpivot.drop(['variable'], axis=1)

# convert days to dates for generic week
dict = {
    'Monday' : '1/09/2023' ,
    'Tuesday' : '1/10/2023' ,
    'Wednesday' : '1/11/2023' ,
    'Thursday' : '1/12/2023' ,
    'Friday' : '1/13/2023' ,
    'Saturday' : '1/14/2023' ,
    'Sunday' : '1/15/2023'
}
df_unpivot=df_unpivot.replace({"value": dict})

df_unpivot['Start_time'] = df_unpivot['value'] + " " + df_unpivot['Start_time']
df_unpivot['End_time'] = df_unpivot['value'] + " " + df_unpivot['End_time']

# clean up extra columns after unpivoting
df_unpivot = df_unpivot.drop(['value'], axis=1)

# write to csv
schedule = "SoC_"
df_unpivot.to_csv(schedule+current_term+ext, index=False, encoding='utf-8-sig')




    


