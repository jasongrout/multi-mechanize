#!/usr/bin/env python
#
#  Copyright (c) 2010 Corey Goldberg (corey@goldb.org)
#  License: GNU LGPLv3
#  
#  This file is part of Multi-Mechanize


import time
from collections import defaultdict
import graph
import numpy as np
from itertools import groupby

def timer_table_vals(timer, interval_secs):
    timer=np.asarray(timer, dtype=float)
    timer_vals=timer[:,1]
    timer_vals.sort()
    n=len(timer_vals)
    graphs={}
    graphs['pct_50_resptime'] = {}
    graphs['pct_80_resptime'] = {}  
    graphs['pct_90_resptime'] = {}  

    summary=dict(count=n,
                 min=timer_vals[0],
                 avg=np.average(timer_vals),
                 max=timer_vals[-1],
                 stdev=timer_vals.std(ddof=1)) #sample standard deviation
    # not exactly percentiles, since I'm not averaging values if 
    # the percentile doesn't fall exactly on a slot.
    for pct in [25,50,80,90,95]:
        summary['pct_%s'%pct]=timer_vals[int((n*pct)//100)]

    splat_series = group_series(timer, interval_secs)
    timer_table=[]
    for i, bucket in splat_series:
        #interval_start = int((i + 1) * interval_secs)
        cnt = len(bucket)
        if cnt == 0:
            row=dict(interval=i, count=0, rate=0, min='N/A', avg='N/A',pct_80='N/A',pct_90='N/A',pct_95='N/A',max='N/A',stdev='N/A')
        else:
            row=dict()
            row['interval'] = i
            row['count'] = cnt
            row['rate'] = cnt / float(interval_secs)
            row['min'] = bucket[0]
            row['avg'] = np.average(bucket)
            row['max'] = bucket[-1]
            row['stdev'] = np.std(bucket, ddof=1) # sample stdev
            # not exactly percentiles, since I'm not averaging values if 
            # the percentile doesn't fall exactly on a slot.
            for pct in [25,50,80,90,95]:
                row['pct_%s'%pct]=bucket[int((cnt*pct)//100)]


        timer_table.append(row)

        # graph data
        graphs['pct_50_resptime'][i] = row['pct_50']
        graphs['pct_80_resptime'][i] = row['pct_80']
        graphs['pct_90_resptime'][i] = row['pct_90']

    return summary, timer_table, graphs    

def output_results(results_dir, results_file, run_time, rampup, ts_interval, user_group_configs=None):
    from jinja2 import Template
    from jinja2 import Environment, FileSystemLoader
    # change this to PackageLoader when we get an installable package
    env = Environment(loader=FileSystemLoader('lib/templates'))
    template = env.get_template('results_template.html')
    template_vars=dict()
    
    results = Results(results_dir + results_file, run_time)
    
    print 'transactions: %i' % results.total_transactions
    print 'errors: %i' % results.total_errors
    print ''
    print 'test start: %s' % results.start_datetime
    print 'test finish: %s' % results.finish_datetime
    print ''
    
    template_vars['total_transactions']=results.total_transactions
    template_vars['total_errors']=results.total_errors
    template_vars['run_time']=run_time
    template_vars['rampup']=rampup
    template_vars['test_start']=results.start_datetime
    template_vars['test_finish']=results.finish_datetime
    template_vars['timeseries_interval']=ts_interval
    template_vars['user_group_configs']=user_group_configs
    
    # Make the "Transactions" timer just another custom timer
    template_vars['timers']={}
    template_vars['graph_filenames']={}
    results.uniq_timer_names.add('transactions')
    for resp_stats in results.resp_stats_list:
        resp_stats.custom_timers['transactions']=[(resp_stats.elapsed_time, resp_stats.trans_time)]

        
    for timer_string in sorted(results.uniq_timer_names):
        timer_points = []  # [elapsed, timervalue]
        for resp_stats in results.resp_stats_list:
            try:
                val = resp_stats.custom_timers[timer_string]
                # the values in a custom timer can either be a single time 
                # delta, a list of time deltas, or a list of 
                # (elapsed time, time delta) tuples
                if not isinstance(val, (list, tuple)):
                    val=[(resp_stats.elapsed_time, val)]
                elif not isinstance(val[0], (list, tuple)):
                    val=[(resp_stats.elapsed_time, v) for v in val]
                # now val is a list of (elapsed time, time delta)
                timer_points.extend(val)
            except (KeyError,IndexError):
                pass
        timer_array=np.asarray(timer_points,dtype=float)

        template_vars['timers'][timer_string]={}
        template_vars['timers'][timer_string]['s'],template_vars['timers'][timer_string]['table'],graph_data=timer_table_vals(timer_points, ts_interval)

        template_vars['graph_filenames'][timer_string]={}
        template_vars['graph_filenames'][timer_string]['resptime']=timer_string+'_response_times_intervals.png'
        template_vars['graph_filenames'][timer_string]['resptime_all']=timer_string+'_response_times.png'
        template_vars['graph_filenames'][timer_string]['throughput']=timer_string+'_throughput.png'

        graph.resp_graph(graph_data['pct_50_resptime'], 
                         graph_data['pct_80_resptime'], 
                         graph_data['pct_90_resptime'], 
                         template_vars['graph_filenames'][timer_string]['resptime'], 
                         results_dir)

        graph.resp_graph_raw(timer_points, 
                             template_vars['graph_filenames'][timer_string]['resptime_all'], 
                             results_dir)


        # all transactions - throughput
        throughput_points = {}  # {intervalstart: numberofrequests}
        interval_secs = 5.0
        splat_series = group_series(timer_points, interval_secs)
        for i, bucket in splat_series:
            throughput_points[i] = (float(len(bucket)) / interval_secs)
        graph.tp_graph(throughput_points, template_vars['graph_filenames'][timer_string]['throughput'], results_dir)



    import os
    with open(os.path.join(results_dir, 'results.html'), 'w') as f:
        f.write(template.render(**template_vars))


class Results(object):
    def __init__(self, results_file_name, run_time):
        self.results_file_name = results_file_name
        self.run_time = run_time
        self.total_transactions = 0
        self.total_errors = 0
        self.uniq_timer_names = set()
        self.uniq_user_group_names = set()
        
        self.resp_stats_list = self.__parse_file()
        
        self.epoch_start = self.resp_stats_list[0].epoch_secs
        self.epoch_finish = self.resp_stats_list[-1].epoch_secs
        self.start_datetime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.epoch_start))
        self.finish_datetime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.epoch_finish))
        
        
        
    def __parse_file(self):
        import json
        import csv
        f = csv.reader(open(self.results_file_name, 'rb'))
        resp_stats_list = []
        for fields in f:
            request_num = int(fields[0])
            elapsed_time = float(fields[1])
            epoch_secs = int(fields[2])
            user_group_name = fields[3]
            trans_time = float(fields[4])
            error = fields[5]
            
            self.uniq_user_group_names.add(user_group_name)
            
            custom_timers = json.loads(fields[6])
            self.uniq_timer_names.update(custom_timers.keys())
            
            r = ResponseStats(request_num, elapsed_time, epoch_secs, user_group_name, trans_time, error, custom_timers)
            
            if elapsed_time < self.run_time:  # drop all times that appear after the last request was sent (incomplete interval)
                resp_stats_list.append(r)
            
            if error != '':
                self.total_errors += 1
                
            self.total_transactions += 1
            
        return resp_stats_list    
   


class ResponseStats(object):
    def __init__(self, request_num, elapsed_time, epoch_secs, user_group_name, trans_time, error, custom_timers):
        self.request_num = request_num
        self.elapsed_time = elapsed_time
        self.epoch_secs = epoch_secs
        self.user_group_name = user_group_name
        self.trans_time = trans_time
        self.error = error
        self.custom_timers = custom_timers
        


def group_series(points, interval):
    """
    Returns [key, [list of values]], where key is the maximal step
    below each of the corresponding values.  The corresponding values will 
    be sorted.
    """
    p=sorted(points,key=lambda x:x[0])
    group_function=lambda x, offset=p[0][0]: interval*int((x[0]-offset)//interval)#+offset
    return [(key,sorted(v for _,v in values)) 
            for key,values in groupby(p,group_function)]
    
if __name__ == '__main__':
    output_results('./', 'results.csv', 60, 30, 10)
