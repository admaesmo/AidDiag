/*
   Licensed to the Apache Software Foundation (ASF) under one or more
   contributor license agreements.  See the NOTICE file distributed with
   this work for additional information regarding copyright ownership.
   The ASF licenses this file to You under the Apache License, Version 2.0
   (the "License"); you may not use this file except in compliance with
   the License.  You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
*/
var showControllersOnly = false;
var seriesFilter = "";
var filtersOnlySampleSeries = true;

/*
 * Add header in statistics table to group metrics by category
 * format
 *
 */
function summaryTableHeader(header) {
    var newRow = header.insertRow(-1);
    newRow.className = "tablesorter-no-sort";
    var cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 1;
    cell.innerHTML = "Requests";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 3;
    cell.innerHTML = "Executions";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 7;
    cell.innerHTML = "Response Times (ms)";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 1;
    cell.innerHTML = "Throughput";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 2;
    cell.innerHTML = "Network (KB/sec)";
    newRow.appendChild(cell);
}

/*
 * Populates the table identified by id parameter with the specified data and
 * format
 *
 */
function createTable(table, info, formatter, defaultSorts, seriesIndex, headerCreator) {
    var tableRef = table[0];

    // Create header and populate it with data.titles array
    var header = tableRef.createTHead();

    // Call callback is available
    if(headerCreator) {
        headerCreator(header);
    }

    var newRow = header.insertRow(-1);
    for (var index = 0; index < info.titles.length; index++) {
        var cell = document.createElement('th');
        cell.innerHTML = info.titles[index];
        newRow.appendChild(cell);
    }

    var tBody;

    // Create overall body if defined
    if(info.overall){
        tBody = document.createElement('tbody');
        tBody.className = "tablesorter-no-sort";
        tableRef.appendChild(tBody);
        var newRow = tBody.insertRow(-1);
        var data = info.overall.data;
        for(var index=0;index < data.length; index++){
            var cell = newRow.insertCell(-1);
            cell.innerHTML = formatter ? formatter(index, data[index]): data[index];
        }
    }

    // Create regular body
    tBody = document.createElement('tbody');
    tableRef.appendChild(tBody);

    var regexp;
    if(seriesFilter) {
        regexp = new RegExp(seriesFilter, 'i');
    }
    // Populate body with data.items array
    for(var index=0; index < info.items.length; index++){
        var item = info.items[index];
        if((!regexp || filtersOnlySampleSeries && !info.supportsControllersDiscrimination || regexp.test(item.data[seriesIndex]))
                &&
                (!showControllersOnly || !info.supportsControllersDiscrimination || item.isController)){
            if(item.data.length > 0) {
                var newRow = tBody.insertRow(-1);
                for(var col=0; col < item.data.length; col++){
                    var cell = newRow.insertCell(-1);
                    cell.innerHTML = formatter ? formatter(col, item.data[col]) : item.data[col];
                }
            }
        }
    }

    // Add support of columns sort
    table.tablesorter({sortList : defaultSorts});
}

$(document).ready(function() {

    // Customize table sorter default options
    $.extend( $.tablesorter.defaults, {
        theme: 'blue',
        cssInfoBlock: "tablesorter-no-sort",
        widthFixed: true,
        widgets: ['zebra']
    });

    var data = {"OkPercent": 25.58076715289033, "KoPercent": 74.41923284710967};
    var dataset = [
        {
            "label" : "FAIL",
            "data" : data.KoPercent,
            "color" : "#FF6347"
        },
        {
            "label" : "PASS",
            "data" : data.OkPercent,
            "color" : "#9ACD32"
        }];
    $.plot($("#flot-requests-summary"), dataset, {
        series : {
            pie : {
                show : true,
                radius : 1,
                label : {
                    show : true,
                    radius : 3 / 4,
                    formatter : function(label, series) {
                        return '<div style="font-size:8pt;text-align:center;padding:2px;color:white;">'
                            + label
                            + '<br/>'
                            + Math.round10(series.percent, -2)
                            + '%</div>';
                    },
                    background : {
                        opacity : 0.5,
                        color : '#000'
                    }
                }
            }
        },
        legend : {
            show : true
        }
    });

    // Creates APDEX table
    createTable($("#apdexTable"), {"supportsControllersDiscrimination": true, "overall": {"data": [0.04024851431658563, 500, 1500, "Total"], "isController": false}, "titles": ["Apdex", "T (Toleration threshold)", "F (Frustration threshold)", "Label"], "items": [{"data": [0.0, 500, 1500, "POST /symptoms"], "isController": false}, {"data": [0.0, 500, 1500, "POST /predict"], "isController": false}, {"data": [0.05708245243128964, 500, 1500, "GET /symptoms"], "isController": false}, {"data": [0.031297709923664124, 500, 1500, "POST /auth/signin"], "isController": false}, {"data": [0.094, 500, 1500, "POST /auth/refresh"], "isController": false}, {"data": [0.06753069577080491, 500, 1500, "GET /auth/me"], "isController": false}, {"data": [0.06951219512195123, 500, 1500, "GET /predictions"], "isController": false}]}, function(index, item){
        switch(index){
            case 0:
                item = item.toFixed(3);
                break;
            case 1:
            case 2:
                item = formatDuration(item);
                break;
        }
        return item;
    }, [[0, 0]], 3);

    // Create statistics table
    createTable($("#statisticsTable"), {"supportsControllersDiscrimination": true, "overall": {"data": ["Total", 3702, 2755, 74.41923284710967, 77364.35629389508, 0, 450063, 61154.0, 182013.6, 213982.99999999997, 300357.44, 4.651454993215057, 2.759315455062321, 2.267162949738026], "isController": false}, "titles": ["Label", "#Samples", "FAIL", "Error %", "Average", "Min", "Max", "Median", "90th pct", "95th pct", "99th pct", "Transactions/s", "Received", "Sent"], "items": [{"data": ["POST /symptoms", 590, 590, 100.0, 71573.73050847453, 0, 242457, 61152.0, 180098.4, 209511.45, 215115.02000000095, 0.742582980501533, 0.14017335379422144, 0.4405546591418258], "isController": false}, {"data": ["POST /predict", 591, 591, 100.0, 60915.954314720846, 0, 240359, 34494.0, 149354.0, 179593.0, 240267.04, 0.7439043271064387, 0.5535018238085888, 0.19587253267011304], "isController": false}, {"data": ["GET /symptoms", 473, 305, 64.48202959830867, 80036.96828752641, 76, 302533, 89521.0, 209230.6, 209582.0, 250426.65999999974, 0.596824339329336, 1.1280259971887427, 0.3226608693162891], "isController": false}, {"data": ["POST /auth/signin", 655, 356, 54.35114503816794, 112948.97557251916, 707, 394140, 112740.0, 250506.19999999998, 266512.8, 392967.52, 0.8240745516971532, 0.41187755242938434, 0.2156757615769893], "isController": false}, {"data": ["POST /auth/refresh", 250, 112, 44.8, 70614.448, 0, 215140, 3576.0, 183942.6, 213762.0, 215078.39, 0.31467638051674895, 0.19052794397061174, 0.3812537898836579], "isController": false}, {"data": ["GET /auth/me", 733, 540, 73.66984993178717, 75735.77762619375, 0, 450063, 60747.0, 179664.6, 242042.3, 389355.5, 0.9221459708008076, 0.2535437024695396, 0.4258256500940388], "isController": false}, {"data": ["GET /predictions", 410, 261, 63.65853658536585, 56502.475609756104, 0, 271252, 31560.5, 152342.2, 179681.9, 239959.3, 0.5160289932777784, 0.0889936148491748, 0.28976483237238665], "isController": false}]}, function(index, item){
        switch(index){
            // Errors pct
            case 3:
                item = item.toFixed(2) + '%';
                break;
            // Mean
            case 4:
            // Mean
            case 7:
            // Median
            case 8:
            // Percentile 1
            case 9:
            // Percentile 2
            case 10:
            // Percentile 3
            case 11:
            // Throughput
            case 12:
            // Kbytes/s
            case 13:
            // Sent Kbytes/s
                item = item.toFixed(2);
                break;
        }
        return item;
    }, [[0, 0]], 0, summaryTableHeader);

    // Create error table
    createTable($("#errorsTable"), {"supportsControllersDiscrimination": false, "titles": ["Type of error", "Number of errors", "% in errors", "% in all samples"], "items": [{"data": ["Non HTTP response code: org.apache.http.NoHttpResponseException/Non HTTP response message: localhost:8000 failed to respond", 197, 7.150635208711433, 5.321447866018368], "isController": false}, {"data": ["500/Internal Server Error", 673, 24.42831215970962, 18.179362506753108], "isController": false}, {"data": ["422/Unprocessable Entity", 125, 4.537205081669692, 3.37655321447866], "isController": false}, {"data": ["403/Forbidden", 1650, 59.89110707803993, 44.570502431118314], "isController": false}, {"data": ["401/Unauthorized", 110, 3.9927404718693285, 2.971366828741221], "isController": false}]}, function(index, item){
        switch(index){
            case 2:
            case 3:
                item = item.toFixed(2) + '%';
                break;
        }
        return item;
    }, [[1, 1]]);

        // Create top5 errors by sampler
    createTable($("#top5ErrorsBySamplerTable"), {"supportsControllersDiscrimination": false, "overall": {"data": ["Total", 3702, 2755, "403/Forbidden", 1650, "500/Internal Server Error", 673, "Non HTTP response code: org.apache.http.NoHttpResponseException/Non HTTP response message: localhost:8000 failed to respond", 197, "422/Unprocessable Entity", 125, "401/Unauthorized", 110], "isController": false}, "titles": ["Sample", "#Samples", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors"], "items": [{"data": ["POST /symptoms", 590, 590, "403/Forbidden", 346, "500/Internal Server Error", 190, "422/Unprocessable Entity", 52, "Non HTTP response code: org.apache.http.NoHttpResponseException/Non HTTP response message: localhost:8000 failed to respond", 2, "", ""], "isController": false}, {"data": ["POST /predict", 591, 591, "403/Forbidden", 367, "Non HTTP response code: org.apache.http.NoHttpResponseException/Non HTTP response message: localhost:8000 failed to respond", 173, "422/Unprocessable Entity", 51, "", "", "", ""], "isController": false}, {"data": ["GET /symptoms", 473, 305, "403/Forbidden", 270, "500/Internal Server Error", 22, "422/Unprocessable Entity", 13, "", "", "", ""], "isController": false}, {"data": ["POST /auth/signin", 655, 356, "500/Internal Server Error", 356, "", "", "", "", "", "", "", ""], "isController": false}, {"data": ["POST /auth/refresh", 250, 112, "401/Unauthorized", 110, "Non HTTP response code: org.apache.http.NoHttpResponseException/Non HTTP response message: localhost:8000 failed to respond", 2, "", "", "", "", "", ""], "isController": false}, {"data": ["GET /auth/me", 733, 540, "403/Forbidden", 442, "500/Internal Server Error", 81, "Non HTTP response code: org.apache.http.NoHttpResponseException/Non HTTP response message: localhost:8000 failed to respond", 17, "", "", "", ""], "isController": false}, {"data": ["GET /predictions", 410, 261, "403/Forbidden", 225, "500/Internal Server Error", 24, "422/Unprocessable Entity", 9, "Non HTTP response code: org.apache.http.NoHttpResponseException/Non HTTP response message: localhost:8000 failed to respond", 3, "", ""], "isController": false}]}, function(index, item){
        return item;
    }, [[0, 0]], 0);

});
