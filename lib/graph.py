#!/usr/bin/env python
#
#  Copyright (c) 2010 Corey Goldberg (corey@goldb.org)
#  License: GNU LGPLv3
#  
#  This file is part of Multi-Mechanize


import sys
import itertools

try:
    import matplotlib
    matplotlib.use('Agg')  # use a non-GUI backend
    from pylab import *
except ImportError:
    print 'ERROR: can not import Matplotlib. install Matplotlib to generate graphs'
    

def resp_graph(lines, points, line_below, boxplots, image_name, timer, dir='./'):
    fig = figure(figsize=(8, 12))  # image dimensions
    fig.suptitle('Timer: '+timer)
    ax1 = fig.add_subplot(311)
    ax2=fig.add_subplot(312,sharex=ax1)
    ax3=fig.add_subplot(313,sharex=ax1)

    ax=ax1
    ax.set_title('Summary of '+timer,size='small')
    #ax.set_xlabel('Elapsed Time In Test (secs)', size='x-small')
    ax.set_ylabel('Response Time (secs)' , size='x-small')
    ax.grid(True, color='#666666')
    ax.tick_params(labelsize='x-small')

    colors=itertools.cycle(['green','orange','purple'])
    for label, line in lines:
        x_seq = sorted(line.keys())
        y_seq = [line[x] for x in x_seq]
        c=colors.next()
        ax.plot(x_seq, y_seq,
                color=c, linestyle='-', linewidth=2.0, marker='o',
                markeredgecolor=c, markerfacecolor='yellow', markersize=2.0,
                label=label)

    ax.legend(loc='best',
              handlelength=1,
              borderpad=1,
              prop=matplotlib.font_manager.FontProperties(size='xx-small'))


    ax=ax2
    ax.set_title('Detail of '+timer,size='small')
    #ax.set_xlabel('Elapsed Time In Test (secs)', size='x-small')
    ax.set_ylabel('Response Time (secs)' , size='x-small')
    ax.grid(True, color='#666666')
    ax.tick_params(labelsize='x-small')

    pos, boxes=zip(*boxplots)
    ax.boxplot(boxes, positions=pos)

    colors=itertools.cycle(['green','orange','purple'])
    for label, line in lines:
        x_seq = sorted(line.keys())
        y_seq = [line[x] for x in x_seq]
        c=colors.next()
        ax.plot(x_seq, y_seq,
                color=c, linestyle='-', linewidth=1.0, marker='o',
                markeredgecolor=c, markerfacecolor='yellow', markersize=1.0,
                label=label)


    ax=ax3
    ax.set_title('Throughput of '+timer,size='small')
    ax.set_xlabel('Elapsed Time In Test (secs)', size='x-small')
    ax.set_ylabel('Timers Per Second (count)' , size='x-small')
    ax.grid(True, color='#666666')
    ax.tick_params(labelsize='x-small')

    throughput_label, throughputs_dict=line_below
    x_seq = sorted(throughputs_dict.keys())
    y_seq = [throughputs_dict[x] for x in x_seq]
    ax.plot(x_seq, y_seq, 
        color='red', linestyle='-', linewidth=0.75, marker='o', 
        markeredgecolor='red', markerfacecolor='yellow', markersize=2.0,
             label=throughput_label)

    savefig(dir + image_name)
