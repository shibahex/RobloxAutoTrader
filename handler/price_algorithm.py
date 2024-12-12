from typing import List, Dict
from datetime import datetime
import time

# MADE BY PMETHOD REWRITTEN OLD ALGORITHM
class SalesVolumeAnalyzer:
    def __init__(self, sales_data: List[Dict[str, float]], volume_data: List[Dict[str, float]], item_id: str):
        """
        Initialize the analyzer with sales and volume data.

        Args:
            sales_data: A list of dictionaries with keys "value" and "date".
            volume_data: A list of dictionaries with keys "value" and "date".
            item_id: The identifier for the item being analyzed.
        """
        self.sales_data = sales_data
        self.volume_data = volume_data
        self.item_id = item_id
        self.values = {}
        self.now = time.time()

    def get_age(self) -> float:
        """Calculate the age based on the oldest sales data entry."""
        if self.sales_data:
            return self.now - self.sales_data[0]["date"]
        return 0.0

    @staticmethod
    def find_extrema(data: List[Dict[str, float]]):
        """Identify low and high points in the dataset."""
        lows, highs = [], []
        for i in range(1, len(data) - 1):
            prev, curr, nxt = data[i - 1]["value"], data[i]["value"], data[i + 1]["value"]
            if prev > curr < nxt:
                lows.append(data[i])
            elif prev < curr > nxt:
                highs.append(data[i])
        return lows, highs

    def segment_data(self, data: List[Dict[str, float]]):
        """Split data into three time-based segments."""
        if not data:
            return [[], [], []]
        start_time = data[0]["date"]
        end_time = data[-1]["date"]
        time_range = end_time - start_time
        segment_length = time_range / 3.0
        segments = [[], [], []]

        for item in data:
            if item["date"] < start_time + segment_length:
                segments[0].append(item)
            elif item["date"] < start_time + 2 * segment_length:
                segments[1].append(item)
            else:
                segments[2].append(item)
        return segments

    @staticmethod
    def calculate_segment_averages(segments: List[List[Dict[str, float]]]) -> List[float]:
        """Calculate average values for each segment."""
        averages = []
        for segment in segments:
            total = sum(item["value"] for item in segment)
            averages.append(total / len(segment) if segment else 0.0)
        return averages

    def adjust_extrema(self, averages: List[float], thirds: List[List[Dict[str, float]]]) -> List[Dict[str, float]]:
        """Filter out segments of the data based on average deviations."""
        avg1 = (averages[0] + averages[1]) / 2.0
        avg2 = (averages[1] + averages[2]) / 2.0
        avg3 = (averages[0] + averages[2]) / 2.0

        if abs(averages[2] - avg1) > avg1:
            return thirds[0] + thirds[1]
        elif abs(averages[0] - avg2) > avg2:
            return thirds[1] + thirds[2]
        elif abs(averages[1] - avg3) > avg3:
            return thirds[0] + thirds[2]
        return thirds[0] + thirds[1] + thirds[2]

    def calculate_low_average(self, data: List[Dict[str, float]]) -> float:
        """Calculate the average of low points."""
        total = sum(item["value"] for item in data)
        return total / len(data) if data else 0.0

    def calculate_volume_average(self, data: List[Dict[str, float]], divisor: float) -> float:
        """Calculate the average of the volume data."""
        total = sum(item["value"] for item in data)
        return total / divisor if divisor else 0.0

    def process(self) -> Dict[str, float]:
        """Process sales and volume data to compute the final values."""
        age = self.get_age()

        # Find lows and highs
        sales_lows, _ = self.find_extrema(self.sales_data)
        _, volume_candles = self.find_extrema(self.volume_data)

        # Segment and adjust sales data
        sales_segments = self.segment_data(sales_lows)
        sales_averages = self.calculate_segment_averages(sales_segments)
        adjusted_sales = self.adjust_extrema(sales_averages, sales_segments)

        # Segment and adjust volume data
        volume_segments = self.segment_data(volume_candles)
        volume_averages = self.calculate_segment_averages(volume_segments)
        adjusted_volume = self.adjust_extrema(volume_averages, volume_segments)

        # Determine volume divisor
        if len(adjusted_volume) == len(volume_candles):
            divisor = 120.0
        else:
            divisor = 80.0

        # Final calculations
        low_average = self.calculate_low_average(adjusted_sales)
        volume_average = self.calculate_volume_average(adjusted_volume, divisor)

        # Store and return results
        self.values[self.item_id] = {
            "value": low_average,
            "volume": volume_average,
            "timestamp": self.now,
            "age": age
        }
        return self.values[self.item_id]
