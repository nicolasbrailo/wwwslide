mAjax({
  url: `/meta`,
  type: 'get',
  dataType: 'json',
  error: console.error,
  success: meta => {
    console.log(meta);
    const revgeo = meta.image_exif.reverse_geo;
    m$('meta').innerText = 
`Image: ${meta.image_path}<br/>
Picture ${meta.image_index} of ${meta.image_count}<br/>
Taken: ${meta.image_exif["EXIF DateTimeOriginal"]}<br/>
Where: ${revgeo.country}, ${revgeo.city}:<br/>
${revgeo.revgeo}<br/>
Cam: ${meta.image_exif["Image Make"]} ${meta.image_exif["Image Model"]}<br/>
`;
  },
});
