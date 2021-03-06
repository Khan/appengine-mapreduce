// Copyright 2011 Google Inc. All Rights Reserved.
package com.google.appengine.tools.mapreduce.impl;

import com.google.appengine.tools.mapreduce.Counter;
import com.google.appengine.tools.mapreduce.Counters;
import com.google.common.collect.Iterables;
import com.google.common.collect.Ordering;

import java.io.Serializable;
import java.util.HashMap;

/**
 */
public class CountersImpl implements Counters {

  private static final long serialVersionUID = -8499952345096458550L;

  private final HashMap<String, CounterImpl> values = new HashMap<String, CounterImpl>();

  @Override public String toString() {
    StringBuilder out = new StringBuilder(getClass().getSimpleName() + "(");
    String separator = "";
    for (String key : Ordering.natural().sortedCopy(values.keySet())) {
      out.append(separator + values.get(key));
      separator = ", ";
    }
    return out + ")";
  }

  @Override
  public Counter getCounter(String name) {
    CounterImpl counter = values.get(name);
    if (counter == null) {
      counter = new CounterImpl(name);
      values.put(name, counter);
    }
    return counter;
  }

  @Override
  public Iterable<? extends Counter> getCounters() {
    return Iterables.unmodifiableIterable(values.values());
  }

  public void addAll(Counters other) {
    for (Counter c : other.getCounters()) {
      getCounter(c.getName()).increment(c.getValue());
    }
  }

  private static class CounterImpl implements Counter, Serializable {
    private static final long serialVersionUID = 5872696485441192885L;

    private final String name;
    private long value = 0L;

    CounterImpl(String name) {
      this.name = name;
    }

    @Override public String toString() {
      return name + "=" + value;
    }

    @Override
    public String getName() {
      return name;
    }

    @Override
    public long getValue() {
      return value;
    }

    @Override
    public void increment(long delta) {
      value += delta;
    }
  }
}
