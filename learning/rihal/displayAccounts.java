private void displayAccounts() {
    VBox accountList = new VBox(10);
    accountList.setPadding(new Insets(10));

    Label account1 = new Label("user1@gmail.com (10 GB used of 15 GB)");
    Label account2 = new Label("user2@gmail.com (2 GB used of 15 GB)");

    PieChart storageChart = new PieChart();
    storageChart.getData().add(new PieChart.Data("Used", 10));
    storageChart.getData().add(new PieChart.Data("Free", 5));

    accountList.getChildren().addAll(account1, account2, storageChart);

    root.setCenter(accountList);
}
