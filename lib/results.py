#!/usr/bin/env python
#
#  Copyright (c) 2010 Corey Goldberg (corey@goldb.org)
#  License: GNU LGPLv3
#  
#  This file is part of Multi-Mechanize


import time
from collections import defaultdict
import graph

def timer_table_vals(timer_points, interval_secs):
    timer_vals=[j for i,j in timer_points]
    graphs={}
    graphs['avg_resptime'] = {}  # {intervalstart: avg_resptime}
    graphs['pct_80_resptime'] = {}  # {intervalstart: 80pct_resptime}
    graphs['pct_90_resptime'] = {}  # {intervalstart: 90pct_resptime}

    summary=dict(count=len(timer_vals),
                 min=min(timer_vals), 
                 avg=average(timer_vals),
                 pct_80=percentile(timer_vals, 80),
                 pct_90=percentile(timer_vals, 90),
                 pct_95=percentile(timer_vals, 95),
                 max=max(timer_vals),
                 stdev=standard_dev(timer_vals))

    splat_series = split_series(timer_points, interval_secs)
    timer_table=[]
    for i, bucket in enumerate(splat_series):
        interval_start = int((i + 1) * interval_secs)
        cnt = len(bucket)
        if cnt == 0:
            row=dict(interval=i+1, count=0, rate=0, min='N/A', avg='N/A',pct_80='N/A',pct_90='N/A',pct_95='N/A',max='N/A',stdev='N/A')
        else:
            row=dict()
            row['interval'] = i+1
            row['count'] = cnt
            row['rate'] = cnt / float(interval_secs)
            row['min'] = min(bucket)
            row['avg'] = average(bucket)
            row['pct_80'] = percentile(bucket, 80)
            row['pct_90'] = percentile(bucket, 90)
            row['pct_95'] = percentile(bucket, 95)
            row['max'] = max(bucket)
            row['stdev'] = standard_dev(bucket)
        timer_table.append(row)

        # graph data
        graphs['avg_resptime'][interval_start] = row['avg']
        graphs['pct_80_resptime'][interval_start] = row['pct_80']
        graphs['pct_90_resptime'][interval_start] = row['pct_90']

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

        template_vars['timers'][timer_string]={}
        template_vars['timers'][timer_string]['s'],template_vars['timers'][timer_string]['table'],graph_data=timer_table_vals(timer_points, ts_interval)

        template_vars['graph_filenames'][timer_string]={}
        template_vars['graph_filenames'][timer_string]['resptime']=timer_string+'_response_times_intervals.png'
        template_vars['graph_filenames'][timer_string]['resptime_all']=timer_string+'_response_times.png'
        template_vars['graph_filenames'][timer_string]['throughput']=timer_string+'_throughput.png'

        graph.resp_graph(graph_data['avg_resptime'], 
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
        splat_series = split_series(timer_points, interval_secs)
        for i, bucket in enumerate(splat_series):
            throughput_points[int((i + 1) * interval_secs)] = (len(bucket) / interval_secs)
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
        


def split_series(points, interval):
    offset = points[0][0]
    maxval = int((points[-1][0] - offset) // interval)
    vals = defaultdict(list)
    for key, value in points:
        vals[(key - offset) // interval].append(value)
    series = [vals[i] for i in xrange(maxval + 1)]
    return series



def average(seq):
    avg = (float(sum(seq)) / len(seq)) 
    return avg



def standard_dev(seq):
    avg = average(seq)
    sdsq = sum([(i - avg) ** 2 for i in seq])
    try:
        stdev = (sdsq / (len(seq) - 1)) ** .5
    except ZeroDivisionError:
        stdev = 0 
    return stdev

    
    
def percentile(seq, percentile):
    i = int(len(seq) * (percentile / 100.0))
    seq.sort()
    return seq[i]




if __name__ == '__main__':
    output_results('./', 'results.csv', 60, 30, 10)
