#!/bin/bash

if [ $# -ne 2 ]; then
    echo Usage $0 SRC DST
    exit -1
fi

SRC=$1
DST=$2

for dir in $(find $DST -maxdepth 1 -type d); do
    if [ $dir != $DST ]; then
	echo Processing $dir
	mkdir -p $dir/images
	mkdir -p $dir/annotations
	mkdir -p $dir/src
	mv $dir/*.jpg $dir/src
	for i in $(find $dir/src/ -name "*.jpg"); do
	    iname=$(basename $i)
	    echo Search $iname
	    sname=$(find $SRC -name $iname | grep src)
	    if [ "x$sname" != "x" ] && [ -f $sname ]; then
		echo Found $sname
		cp $sname $dir/images
	    else
		echo Not found $iname
	    fi
	done
    fi
done
