package com.example.syncly;

import android.content.Context;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.TextView;
import java.util.List;
import java.util.Map;

public class FileListAdapter extends ArrayAdapter<Map<String, String>> {
    private final Context context;
    private final List<Map<String, String>> files;

    public FileListAdapter(Context context, List<Map<String, String>> files) {
        super(context, R.layout.list_file_item, files);
        this.context = context;
        this.files = files;
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

        Map<String, String> file = files.get(position);
        holder.textViewFileName.setText(file.get("name") + " (" + file.get("size") + ")");
        return convertView;
    }

    private static class ViewHolder {
        TextView textViewFileName;
    }
}