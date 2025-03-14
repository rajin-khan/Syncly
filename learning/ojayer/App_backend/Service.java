package org.example;

import java.util.List;
import java.util.Map;

public interface Service {
    void authenticate(int bucketNumber, String userId);
    List<Map<String, Object>> listFiles(String query);
    long[] checkStorage(); // Returns [limit, usage]
}