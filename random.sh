#!/bin/bash



for i in $(ls $1/train/annotations/*.xml); do

    NO=$(( RANDOM % 100 ))

    if [ $NO -gt 80 ]; then
	echo Do nothing
    else
	echo Move
	mv $i $1/validation/annotations
	jpg=$(echo $i | sed -e 's/xml/jpg/');
	jpg=$(basename $jpg)
	mv $1/train/images/$jpg  $1/validation/images
    fi
done
