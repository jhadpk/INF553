import os
import sys
from pyspark import SparkConf, SparkContext
import time
import math

# os.environ["PYSPARK_PYTHON"] = "/usr/local/bin/python3.6"
# export PYSPARK_PYTHON=python3.6


def get_pearson_coefficient(neighbour_id, users_list, business_ratings, average_business_rating):
    average_neighbour_rating = business_avg_rating_map.get(neighbour_id)
    neighbour_business_ratings = business_rating_map.get(neighbour_id)
    all_business_ratings = []
    all_neighbour_ratings = []
    for current_user_id in users_list:
        if neighbour_business_ratings.get(current_user_id):
            business_rating = business_ratings.get(current_user_id)
            neighbour_rating = neighbour_business_ratings.get(current_user_id)
            all_business_ratings.append(business_rating)
            all_neighbour_ratings.append(neighbour_rating)
    if len(all_business_ratings) != 0:
        numerator = 0
        denominator_business = 0
        denominator_neighbour = 0
        for j in range(0, len(all_business_ratings)):
            normalized_business_rating = all_business_ratings[j] - average_business_rating
            normalized_neighbour_rating = all_neighbour_ratings[j] - average_neighbour_rating
            numerator += normalized_business_rating * normalized_neighbour_rating
            denominator_business += normalized_business_rating * normalized_business_rating
            denominator_neighbour += normalized_neighbour_rating * normalized_neighbour_rating
        denominator = math.sqrt(denominator_business * denominator_neighbour)
        if denominator == 0:
            if numerator == 0:
                pearson_coefficient = 1
            else:
                return -1
        else:
            pearson_coefficient = numerator / denominator
    else:
        pearson_coefficient = float(average_business_rating / average_neighbour_rating)  # default voting
    return pearson_coefficient


def get_prediction(pearson_coeff_and_rating_list, default_average):
    prediction_weight_sum = 0
    pearson_coefficient_sum = 0
    neighbourhood_cutoff = 50
    pearson_coeff_and_rating_list.sort(key=lambda x: x[0], reverse=True)
    if len(pearson_coeff_and_rating_list) == 0:
        # couldnt get valid pearson coeff b/w businesses, returning avg of avg_user_rating and avg_business_rating
        return default_average
    neighbourhood = min(len(pearson_coeff_and_rating_list), neighbourhood_cutoff)
    for x in range(neighbourhood):
        prediction_weight_sum += pearson_coeff_and_rating_list[x][0] * pearson_coeff_and_rating_list[x][
            1]  # pearson_coeff * rating
        pearson_coefficient_sum += abs(pearson_coeff_and_rating_list[x][0])
    prediction = prediction_weight_sum / pearson_coefficient_sum
    return min(5.0, max(0.0, prediction))


def item_based_prediction(test_data):
    user = test_data[0]
    business = test_data[1]
    if business not in business_rating_map:
        # Cold start (new business)
        if len(list(user_rating_map.get(user))) == 0:
            # user is new too
            return user, business, "2.5"
        return user, business, str(user_avg_rating_map.get(user))
    else:
        users_list = list(business_rating_map.get(business))
        business_ratings = business_rating_map.get(business)
        average_business_rating = business_avg_rating_map.get(business)
        if user_rating_map.get(user) is None:
            # Cold start (new user)
            return user, business, str(average_business_rating)
        else:
            businesses_list = list(user_rating_map.get(user))  # list() gives list of keys in dict
            if len(businesses_list) != 0:  # user has given ratings
                pearson_coeff_and_rating_list = []
                for neighbour_business_id in businesses_list:
                    current_neighbour_rating = business_rating_map.get(neighbour_business_id).get(user)
                    pearson_coefficient = get_pearson_coefficient(neighbour_business_id, users_list, business_ratings, average_business_rating)
                    if pearson_coefficient > 0:
                        if pearson_coefficient > 1:
                            pearson_coefficient = 1 / pearson_coefficient
                        pearson_coeff_and_rating_list.append((pearson_coefficient, current_neighbour_rating))
                prediction = get_prediction(pearson_coeff_and_rating_list, (user_avg_rating_map.get(user) + average_business_rating) / 2)
                return user, business, min(5.0, max(0.0, prediction))
            else:
                # new user (no such user in yelp_test.csv)
                return user, business, str(average_business_rating)


def write_to_file(output_file, prediction_list):
    f = open(output_file, 'w')
    f.write("user_id, business_id, prediction\n")
    for i in range(len(prediction_list)):
        f.write(str(prediction_list[i][0]) + "," + str(prediction_list[i][1]) + "," + str(prediction_list[i][2]) + "\n")
    f.close()


start_time = time.time()

# time /home/local/spark/latest/bin/spark-submit task2_1.py $ASNLIB/publicdata/yelp_train.csv $ASNLIB/publicdata/yelp_val.csv task2-output1a.csv
input_file_train = sys.argv[1]
input_file_test = sys.argv[2]
output_file = sys.argv[3]
# input_file_train = 'dataset/yelp_train.csv'
# input_file_test = 'dataset/yelp_val.csv'
# output_file = 'output/task2_1.csv'

conf = SparkConf().setAppName("INF553").setMaster('local[*]')
sc = SparkContext(conf=conf)
sc.setLogLevel("ERROR")
train_rdd = sc.textFile(input_file_train)
train_header = train_rdd.first()
train_data = train_rdd.filter(lambda x: x != train_header).map(lambda x: x.split(','))

test_rdd = sc.textFile(input_file_test)
test_header = test_rdd.first()
test_rdd = test_rdd.filter(lambda x: x != test_header)

user_rating_map = train_data.map(lambda x: ((x[0]), ((x[1]), float(x[2])))).groupByKey().sortByKey(True).mapValues(dict).collectAsMap()  # user key
business_rating_map = train_data.map(lambda x: ((x[1]), ((x[0]), float(x[2])))).groupByKey().sortByKey(True).mapValues(dict).collectAsMap()  # business key
user_avg_rating_map = train_data.map(lambda x: (x[0], float(x[2]))).groupByKey().mapValues(lambda x: sum(x) / len(x)).collectAsMap()  # userId <-> avg rating
business_avg_rating_map = train_data.map(lambda x: (x[1], float(x[2]))).groupByKey().mapValues(lambda x: sum(x) / len(x)).collectAsMap()  # businessId <-> avg rating

test_matrix = test_rdd.map(lambda x: x.split(",")).sortBy(lambda x: ((x[0]), (x[1]))).persist()
prediction_list = test_matrix.map(item_based_prediction).collect()

write_to_file(output_file, prediction_list)

# output_rdd = sc.textFile(output_file)
# output_header = output_rdd.first()
# output_data = output_rdd.filter(lambda x: x != output_header).map(lambda x: x.split(','))
# output_data_dict = output_data.map(lambda x: (((x[0]), (x[1])), float(x[2])))
# test_data_dict = test_rdd.map(lambda x: x.split(",")).map(lambda x: (((x[0]), (x[1])), float(x[2])))
# joined_data = test_data_dict.join(output_data_dict).map(lambda x: (abs(x[1][0] - x[1][1])))
#
# diff_0_to_1 = joined_data.filter(lambda x: x >= 0 and x < 1).count()
# diff_1_to_2 = joined_data.filter(lambda x: x >= 1 and x < 2).count()
# diff_2_to_3 = joined_data.filter(lambda x: x >= 2 and x < 3).count()
# diff_3_to_4 = joined_data.filter(lambda x: x >= 3 and x < 4).count()
# diff_more_than_4 = joined_data.filter(lambda x: x >= 4).count()
# print(">=0 and <1: ", diff_0_to_1)
# print(">=1 and <2: ", diff_1_to_2)
# print(">=2 and <3: ", diff_2_to_3)
# print(">=3 and <4: ", diff_3_to_4)
# print(">=4: ", diff_more_than_4)
# rmse_rdd = joined_data.map(lambda x: x ** 2).reduce(lambda x, y: x + y)
# rmse = math.sqrt(rmse_rdd / output_data_dict.count())
# print("RMSE", rmse)

print("Duration : ", time.time() - start_time)

# >=0 and <1:  94269
# >=1 and <2:  38736
# >=2 and <3:  7755
# >=3 and <4:  1283
# >=4:  1
# RMSE 1.070173169614003
# Duration :  77.43102025985718
# Vocareum
# Duration :  80.88700485229492
# real    1m23.310s
# user    0m24.456s
# sys     0m2.748s
