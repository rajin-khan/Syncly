package com.example.syncly;

import android.content.Context;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.TextView;
import java.util.List;

public class FileListAdapter extends ArrayAdapter<String> {
    private final Context context;
    private final List<String> fileNames;

    public FileListAdapter(Context context, List<String> fileNames) {
        super(context, R.layout.list_file_item, fileNames);
        this.context = context;
        this.fileNames = fileNames;
    }

    @Override
    public View getView(int position, View convertView, ViewGroup parent) {
        ViewHolder holder;
        if (convertView == null) {
            convertView = LayoutInflater.from(context).inflate(R.layout.list_file_item, parent, false);
            holder = new ViewHolder();
            holder.textViewFileName = convertView.findViewById(R.id.text_view_file_name);
            convertView.setTag(holder);
        } else {
            holder = (ViewHolder) convertView.getTag();
        }

        holder.textViewFileName.setText(fileNames.get(position));
        return convertView;
    }

    private static class ViewHolder {
        TextView textViewFileName;
    }
}